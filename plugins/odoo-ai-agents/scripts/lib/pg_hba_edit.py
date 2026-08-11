"""pg_hba_edit.py - parse and rewrite a pg_hba.conf managed block, on the HOST.

The transform half of the local-passwordless-auth setup step. It is a PURE TEXT
filter - input on stdin (or ``--file``), the rewritten file on stdout - so it is
exercisable with no PostgreSQL, no Docker, and no privilege, which is the whole
reason it is not an inline shell heredoc: the rule it emits is a security
boundary, and a security boundary that can only be tested by editing a live
cluster is not tested.

The step that drives it (``scripts/setup-steps/48-db-local-auth.sh``) owns every
privileged action - reading the file out of the cluster, backing it up, writing
the result back through an atomic same-directory rename, reloading, and verifying
by reconnecting. This file owns only the bytes.

CLI contract
------------
  python3 pg_hba_edit.py apply --user U [--user U2 ...] --address A [--address A2 ...]
                               [--file F]
      Emit the whole file with EXACTLY ONE managed block, containing one rule per
      (role, address) pair, inserted immediately BEFORE the first non-comment,
      non-blank rule line. An existing managed block is REPLACED, never appended
      to, so re-running converges: two applies with the same arguments produce
      byte-identical output.
      Repeating --user is what keeps a cluster shared by two declared roles at one
      NARROW line each instead of one wide line for both.
      Exit 0 on success, 2 on a usage error or a refused rule (see below).

  python3 pg_hba_edit.py revert [--file F]
      Emit the whole file with the managed block removed and nothing else
      changed. Round-trips exactly: revert(apply(x)) == x.

  python3 pg_hba_edit.py render --user U [--user U2 ...] --address A [--address A2 ...]
      Emit ONLY the block, for a caller that must hand a human the exact lines to
      add by hand (the native arm, which never edits a system file itself).

Why the emitted rule is shaped the way it is
--------------------------------------------
  host    all     <db_user>    <address>/<prefixlen>    trust

  * FIRST-MATCH-WINS is the property that makes the insertion point load-bearing,
    not cosmetic. A stock file ends with a catch-all (``host all all all
    scram-sha-256``); a rule added after it can never match anything.
  * ``user`` is the DECLARED role and never a WIDENING token: only the role Odoo
    connects as gets passwordless access, and every other role on the cluster
    keeps its current method. pg_hba spells that widening three ways and all
    three are refused - ``all`` (every role), ``+role`` (every member of a role)
    and ``@file`` (every role named in a file this rule cannot read).
  * ``address`` carries a single-host prefix length - ``/32`` for IPv4, ``/128``
    for IPv6 - and nothing wider. A ``/16`` bridge subnet would additionally
    trust every other container on that bridge, which is not where the plugin's
    connections come from. A BARE address is refused too: to PostgreSQL an
    address with no prefix length is a HOST NAME, so it would silently match
    something else entirely.
  * ``database`` is the one axis that cannot be narrowed: ephemeral database
    names are minted at runtime, so no enumerable list exists, and the
    maintenance database must stay reachable because every ``odoo-bin`` run opens
    it before any module loads.

Every one of those is enforced below and refuses with exit 2 rather than emitting
a wider rule than asked for: a malformed call must never become a broad trust
line.
"""

from __future__ import print_function

import re
import sys

try:
    import ipaddress
except ImportError:  # pragma: no cover - the regex gate below is then the only one
    ipaddress = None

EXIT_OK = 0
EXIT_USAGE = 2

MANAGED_BEGIN = "# BEGIN odoo-ai-agents managed block - generated, do not edit by hand"
MANAGED_END = "# END odoo-ai-agents managed block"

# The single-host prefix length per address family. Anything wider is refused:
# these two numbers ARE the "narrow on the address axis" half of the rule.
_HOST_PREFIX = {4: 32, 6: 128}

_IPV4 = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")
_IPV6 = re.compile(r"^[0-9A-Fa-f:]+$")


class Refused(Exception):
    """A rule that would have been wider than asked for, or unparseable."""


def _is_parseable_literal(addr, family):
    """Does the stdlib parser read `addr` as an address of `family`?

    The character-class regexes above accept strings PostgreSQL cannot parse -
    measured: both ``1:2:3:4:5:6:7:8:9:10:11`` and ``:::::`` satisfy
    ``^[0-9A-Fa-f:]+$`` - and an unparseable address does not fail closed. It
    makes the whole FILE unparseable, and the postmaster REFUSES TO START on
    that, so the cluster stays up until the next restart and then does not come
    back. ``ipaddress.ip_address`` is the authority here; the regex stays as the
    cheap gate that decides which family a refusal names.
    """
    if ipaddress is None:
        return True
    try:
        parsed = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return parsed.version == family


def _family(addr):
    """4 / 6 for an address LITERAL; raises Refused for anything else.

    A host name is refused rather than resolved: resolution happens on the
    server, at connect time, against whatever the cluster's resolver says - so a
    name in a trust rule authorises a moving target.
    """
    m = _IPV4.match(addr)
    if m:
        if (all(0 <= int(g) <= 255 for g in m.groups())
                and _is_parseable_literal(addr, 4)):
            return 4
        raise Refused("{a!r} is not a valid IPv4 address".format(a=addr))
    if ":" in addr and _IPV6.match(addr):
        if _is_parseable_literal(addr, 6):
            return 6
        raise Refused(
            "{a!r} is not a valid IPv6 address. PostgreSQL refuses to START on a "
            "pg_hba.conf it cannot parse, so emitting it would take the cluster "
            "down at its next restart.".format(a=addr))
    raise Refused(
        "{a!r} is not an IP address literal. A pg_hba address that is not a literal is "
        "read as a HOST NAME, so the rule would authorise whatever that name resolves "
        "to at connect time.".format(a=addr))


def normalize_address(spec):
    """Validate ``<addr>/<prefixlen>`` and return it unchanged.

    Refuses a bare address (no prefix length) and any prefix wider than a single
    host. This is the one place the width of the authorisation is decided, so it
    is the one place a mistake could widen it.
    """
    if not spec or "/" not in spec:
        raise Refused(
            "address {s!r} carries no prefix length. A bare address in pg_hba.conf is a "
            "HOST NAME, not a single host - refusing to emit it.".format(s=spec))
    addr, _, prefix = spec.rpartition("/")
    fam = _family(addr)
    if not prefix.isdigit():
        raise Refused("prefix length {p!r} in {s!r} is not a number".format(p=prefix, s=spec))
    want = _HOST_PREFIX[fam]
    if int(prefix) != want:
        raise Refused(
            "{s!r} is wider than one host: an IPv{f} rule must carry /{w}. A wider prefix "
            "trusts every other address in that range.".format(s=spec, f=fam, w=want))
    return "{a}/{p}".format(a=addr, p=int(prefix))


def normalize_user(user):
    """Validate the role field. Every token that widens it is refused.

    pg_hba's USER column has THREE role-widening spellings, not one, and each
    turns "this one role" into "more roles than were asked for":
      * ``all``  - every role on the cluster;
      * ``+foo`` - every MEMBER of role foo, transitively;
      * ``@f``   - every role NAMED IN THE FILE f, whose content this plugin
                   neither wrote nor can see.
    All three are refused with the same explain-why text, because the module's
    contract - only the role Odoo connects as gets passwordless access - is false
    the moment any of them is emitted.
    """
    if not user or not user.strip():
        raise Refused("the role field is empty - refusing to emit a rule with no role")
    user = user.strip()
    if user.lower() == "all":
        raise Refused(
            "the role field may not be 'all': that would give EVERY role on the cluster "
            "passwordless access, not the one role Odoo connects as")
    if user.startswith("+"):
        raise Refused(
            "the role field may not start with '+': to PostgreSQL {u!r} means every "
            "MEMBER of role {r!r}, not the one role Odoo connects as. Declare the role "
            "itself.".format(u=user, r=user[1:]))
    if user.startswith("@"):
        raise Refused(
            "the role field may not start with '@': to PostgreSQL {u!r} means every role "
            "listed in the file {f!r}, whose contents this rule cannot see - so the set "
            "of roles it authorises is unknowable. Declare the role itself.".format(
                u=user, f=user[1:]))
    if re.search(r"[\s,\"]", user):
        raise Refused(
            "role {u!r} contains whitespace, a comma or a quote - a pg_hba field cannot "
            "carry those unquoted, and quoting would change what it matches".format(u=user))
    return user


def render_rule(db_user, address):
    """One validated ``host all <role> <addr>/<len> trust`` line (no newline)."""
    return "host    all     {u}    {a}    trust".format(
        u=normalize_user(db_user), a=normalize_address(address))


def render_block(db_users, addresses):
    """The whole delimited block, newline-terminated: one rule per (role, address).

    `db_users` may be a single role or a sequence of them - a cluster shared by
    two declared instances with different roles gets one narrow line each, never
    one wide line covering both.

    Pairs are de-duplicated in first-seen order: a container attached to two
    networks that share a gateway must not produce the same line twice.
    """
    if isinstance(db_users, str):
        db_users = [db_users]
    seen, rules = set(), []
    for user in db_users:
        for addr in addresses:
            rule = render_rule(user, addr)
            if rule in seen:
                continue
            seen.add(rule)
            rules.append(rule)
    if not rules:
        raise Refused(
            "a role and at least one address are both required - refusing to emit an "
            "empty managed block")
    return "".join([MANAGED_BEGIN + "\n"] + [r + "\n" for r in rules] + [MANAGED_END + "\n"])


def _split(text):
    """Lines WITH their endings, so every untouched line survives byte for byte."""
    return text.splitlines(True)


def strip_block(text):
    """`text` with the managed block removed; everything else untouched.

    An unterminated block (a BEGIN with no END) is REFUSED rather than guessed
    at: dropping to end-of-file would delete any rule a human appended after it,
    and dropping one line would leave a live marker behind.
    """
    lines = _split(text)
    out, i = [], 0
    while i < len(lines):
        if lines[i].strip() == MANAGED_BEGIN:
            start = i
            i += 1
            while i < len(lines) and lines[i].strip() != MANAGED_END:
                i += 1
            if i >= len(lines):
                raise Refused(
                    "the managed block opened at line {n} is never closed by {end!r}. "
                    "Refusing to guess where it ends - restore the timestamped backup the "
                    "step printed, or delete the marker by hand.".format(
                        n=start + 1, end=MANAGED_END))
            i += 1
            continue
        out.append(lines[i])
        i += 1
    return "".join(out)


def _first_rule_index(lines):
    """Index of the first non-comment, non-blank line, or len(lines).

    pg_hba.conf is FIRST-MATCH-WINS, so the block must precede whatever is there
    already - including a catch-all that would otherwise swallow the connection.
    Anchoring on the first RULE (rather than on the end of the file, or on a
    matched catch-all) makes that true for any file, including one whose rules a
    human has reordered.
    """
    for idx, raw in enumerate(lines):
        stripped = raw.strip()
        if stripped and not stripped.startswith("#"):
            return idx
    return len(lines)


def insert_block(text, db_users, addresses):
    """`text` with EXACTLY ONE managed block above the first rule line.

    Any existing block is stripped first, so this is idempotent by construction
    rather than by the caller remembering to check.
    """
    block = render_block(db_users, addresses)
    lines = _split(strip_block(text))
    at = _first_rule_index(lines)
    if at < len(lines) or not lines:
        return "".join(lines[:at]) + block + "".join(lines[at:])
    # Comments/blanks only: append, ensuring the last line is terminated so the
    # marker cannot end up glued to a trailing comment.
    if lines and not lines[-1].endswith("\n"):
        lines[-1] = lines[-1] + "\n"
    return "".join(lines) + block


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _read_input(path):
    if path:
        with open(path, "rb") as fh:
            return fh.read().decode("utf-8", "surrogateescape")
    data = sys.stdin.buffer.read() if hasattr(sys.stdin, "buffer") else sys.stdin.read()
    if isinstance(data, bytes):
        return data.decode("utf-8", "surrogateescape")
    return data


def _write_output(text):
    data = text.encode("utf-8", "surrogateescape")
    if hasattr(sys.stdout, "buffer"):
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
    else:
        sys.stdout.write(text)


_USAGE = (
    "Usage: pg_hba_edit.py apply  --user U [--user U2 ...] --address A [--address A2 ...]\n"
    "                             [--file F]\n"
    "       pg_hba_edit.py revert [--file F]\n"
    "       pg_hba_edit.py render --user U [--user U2 ...] --address A [--address A2 ...]\n"
    "The rewritten file (or the block alone, for `render`) goes to stdout; the\n"
    "input file is never modified in place.\n"
)


def _parse(argv):
    opts = {"users": [], "addresses": [], "file": ""}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--user" and i + 1 < len(argv):
            opts["users"].append(argv[i + 1]); i += 2; continue
        if arg == "--address" and i + 1 < len(argv):
            opts["addresses"].append(argv[i + 1]); i += 2; continue
        if arg == "--file" and i + 1 < len(argv):
            opts["file"] = argv[i + 1]; i += 2; continue
        raise Refused("unrecognised argument {a!r}".format(a=arg))
    return opts


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        sys.stderr.write(_USAGE)
        return EXIT_USAGE
    cmd, rest = argv[0], argv[1:]
    try:
        opts = _parse(rest)
        if cmd == "render":
            _write_output(render_block(opts["users"], opts["addresses"]))
            return EXIT_OK
        if cmd == "apply":
            _write_output(insert_block(
                _read_input(opts["file"]), opts["users"], opts["addresses"]))
            return EXIT_OK
        if cmd == "revert":
            _write_output(strip_block(_read_input(opts["file"])))
            return EXIT_OK
    except Refused as exc:
        sys.stderr.write("pg_hba_edit: REFUSED - {exc}\n".format(exc=exc))
        sys.stderr.write("  Nothing was emitted, so nothing can be written back.\n")
        return EXIT_USAGE
    except (IOError, OSError) as exc:
        sys.stderr.write("pg_hba_edit: cannot read input - {exc}\n".format(exc=exc))
        return EXIT_USAGE
    sys.stderr.write("pg_hba_edit: unknown subcommand {cmd!r}.\n".format(cmd=cmd))
    sys.stderr.write(_USAGE)
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
