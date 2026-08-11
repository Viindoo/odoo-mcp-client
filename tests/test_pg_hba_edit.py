"""Behavior tests for scripts/lib/pg_hba_edit.py - the pg_hba.conf transform.

The rule this file emits is a SECURITY BOUNDARY: one role, one address, no
password. So the properties that matter are not "the text changed" but "the
authorisation is exactly as narrow as asked for, it lands where it can actually
match, and it can be undone byte for byte".

Every case runs with NO PostgreSQL, NO Docker and NO privilege - which is the
entire reason the transform is a host-side library instead of an inline shell
heredoc inside the privileged step. A boundary that can only be tested by editing
a live cluster does not get tested.
"""

import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
HBA_EDIT = PLUGIN / "scripts" / "lib" / "pg_hba_edit.py"


def _import_hba_edit():
    spec = importlib.util.spec_from_file_location("pg_hba_edit_under_test", HBA_EDIT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pg_hba_edit_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


MOD = _import_hba_edit()

# A stock container image's file, trimmed to the shape that matters: comments, a
# header, the local/loopback rules, and the CATCH-ALL last. The catch-all is the
# whole reason insertion position is a correctness property.
STOCK = """\
# PostgreSQL Client Authentication Configuration File
# ===================================================
#
# TYPE  DATABASE        USER            ADDRESS                 METHOD

# "local" is for Unix domain socket connections only
local   all             all                                     trust
# IPv4 local connections:
host    all             all             127.0.0.1/32            trust
# IPv6 local connections:
host    all             all             ::1/128                 trust
host all all all scram-sha-256
"""


def _rule_lines(text):
    """Every non-comment, non-blank line, in file order."""
    return [ln for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]


def _managed_lines(text):
    """The rule lines BETWEEN the managed markers."""
    out, inside = [], False
    for ln in text.splitlines():
        if ln.strip() == MOD.MANAGED_BEGIN:
            inside = True
            continue
        if ln.strip() == MOD.MANAGED_END:
            inside = False
            continue
        if inside and ln.strip() and not ln.strip().startswith("#"):
            out.append(ln)
    return out


def _fields(line):
    """A pg_hba line as its five positional fields."""
    parts = line.split()
    assert len(parts) == 5, f"expected `type db user address method`, got {parts!r}"
    return dict(zip(("type", "database", "user", "address", "method"), parts))


# --------------------------------------------------------------------------- #
# Guard 11 - position, which is the difference between working and silently not
# --------------------------------------------------------------------------- #
def test_managed_block_is_inserted_above_the_first_rule_line():
    """pg_hba.conf is FIRST-MATCH-WINS, so a rule below the catch-all is dead text.

    This is not a style preference. The stock image already ships
    `host all all 127.0.0.1/32 trust`, and host TCP through a published container
    port STILL demands a password - because that connection arrives from the
    bridge gateway and is swallowed by the catch-all further down. A block
    appended at the end reproduces exactly that silent no-op.
    """
    out = MOD.insert_block(STOCK, "odoo", ["172.30.0.1/32"])
    rules = _rule_lines(out)
    assert rules[0] == "host    all     odoo    172.30.0.1/32    trust", (
        f"the managed rule must be the FIRST rule in the file; got {rules[0]!r}"
    )
    catch_all = [i for i, r in enumerate(rules) if r.split()[-1] == "scram-sha-256"]
    assert catch_all and catch_all[0] > 0, (
        "the managed rule must precede the catch-all, or it can never match"
    )


def test_insertion_point_is_the_first_rule_not_the_end_of_the_comment_header():
    """Anchoring on the first RULE (not on a line count, not on a matched pattern)
    is what makes the position right for a file whose rules a human has reordered."""
    reordered = "# hdr\n\nhost all all all reject\nlocal all all trust\n"
    out = MOD.insert_block(reordered, "odoo", ["10.1.2.3/32"])
    assert _rule_lines(out)[0].split()[3] == "10.1.2.3/32"


def test_a_file_with_no_rule_at_all_still_gets_a_terminated_block():
    """A comments-only file must gain a well-formed block, not a marker glued onto
    a trailing comment - the shape that would make the next revert unparseable."""
    out = MOD.insert_block("# only a comment, no newline at EOF", "odoo", ["10.0.0.1/32"])
    assert out.splitlines()[-1] == MOD.MANAGED_END
    assert _managed_lines(out) == ["host    all     odoo    10.0.0.1/32    trust"]


# --------------------------------------------------------------------------- #
# Guard 12 - idempotence, by replacement rather than by the caller remembering
# --------------------------------------------------------------------------- #
def test_reapplying_replaces_the_managed_block_and_never_duplicates():
    """Setup is re-run freely, so three applies must converge on ONE block.

    Appending instead would grow the file without bound and leave stale rules for
    a gateway that has since changed - trusting an address nothing arrives from.
    """
    once = MOD.insert_block(STOCK, "odoo", ["172.30.0.1/32"])
    twice = MOD.insert_block(once, "odoo", ["172.30.0.1/32"])
    thrice = MOD.insert_block(twice, "odoo", ["172.30.0.1/32"])
    assert twice == once, "the second apply must be byte-identical to the first"
    assert thrice == twice, "and so must the third"
    assert once.count(MOD.MANAGED_BEGIN) == 1
    assert len(_managed_lines(once)) == 1


def test_reapplying_with_a_new_address_replaces_the_stale_rule():
    """A bridge gateway is not a stable identifier: recreating a docker network can
    change it. The new rule must REPLACE the old one, so no line is left behind
    authorising an address this host no longer connects from."""
    old = MOD.insert_block(STOCK, "odoo", ["172.30.0.1/32"])
    new = MOD.insert_block(old, "odoo", ["10.44.0.1/32"])
    assert _managed_lines(new) == ["host    all     odoo    10.44.0.1/32    trust"]
    assert "172.30.0.1" not in new


def test_two_declared_roles_on_one_cluster_get_one_narrow_line_each():
    """A cluster shared by two declared instances must not be collapsed into one
    wide rule. Two roles means two lines - the narrowness is per role."""
    out = MOD.insert_block(STOCK, ["odoo", "odoo_ci"], ["172.30.0.1/32"])
    users = [_fields(ln)["user"] for ln in _managed_lines(out)]
    assert users == ["odoo", "odoo_ci"]
    assert "all" not in users


def test_a_gateway_shared_by_two_networks_is_not_written_twice():
    """Two attached networks may report the same gateway; the file must not gain
    the same line twice, or the block stops being byte-stable across runs."""
    out = MOD.insert_block(STOCK, "odoo", ["172.30.0.1/32", "172.30.0.1/32"])
    assert len(_managed_lines(out)) == 1


# --------------------------------------------------------------------------- #
# Guard 13 - everything else survives, character for character
# --------------------------------------------------------------------------- #
def test_transform_preserves_every_pre_existing_line_including_comments():
    """The plugin is editing a file it does not own. Every line that was there
    before must still be there, in order, unchanged - including the comments a
    human relies on to read the file."""
    before = STOCK.splitlines()
    after = MOD.insert_block(STOCK, "odoo", ["172.30.0.1/32"]).splitlines()
    kept = [ln for ln in after
            if ln.strip() not in (MOD.MANAGED_BEGIN, MOD.MANAGED_END)
            and "172.30.0.1/32" not in ln]
    assert kept == before, "a pre-existing line was dropped, reordered or rewritten"


def test_transform_preserves_a_crlf_file_and_a_missing_final_newline():
    """Line endings and a missing trailing newline are content too: rewriting them
    turns a diff a human is reading into noise, and can break a strict parser."""
    crlf = "# h\r\nlocal all all trust\r\nhost all all all reject"
    out = MOD.insert_block(crlf, "odoo", ["10.0.0.1/32"])
    assert "# h\r\n" in out and "local all all trust\r\n" in out
    assert out.endswith("host all all all reject")


# --------------------------------------------------------------------------- #
# Guard 14 - the shape of the authorisation, asserted on PARSED FIELDS
#
# Asserting on fields (not on the rendered string) is what makes this guard
# survive a reformatting and still fail on a widening.
# --------------------------------------------------------------------------- #
def test_transform_emits_a_single_host_slash32_for_the_declared_role_never_all():
    """`host all <declared role> <addr>/32 trust` - narrow on both axes it can be.

    `database` is `all` by necessity (ephemeral names are minted at runtime and
    the maintenance database must stay reachable); `user` and `address` are not,
    and each is one keystroke away from authorising far more than was asked.
    """
    out = MOD.insert_block(STOCK, "odoo", ["172.30.0.1/32"])
    lines = _managed_lines(out)
    assert len(lines) == 1
    f = _fields(lines[0])
    assert f["type"] == "host"
    assert f["database"] == "all"
    assert f["user"] == "odoo" and f["user"] != "all"
    assert f["address"] == "172.30.0.1/32"
    assert f["address"].endswith("/32"), "a single host, never a subnet"
    assert f["method"] == "trust"


def test_an_ipv6_gateway_gets_a_slash128_and_nothing_wider():
    out = MOD.insert_block(STOCK, "odoo", ["fd00::1/128"])
    assert _fields(_managed_lines(out)[0])["address"] == "fd00::1/128"


@pytest.mark.parametrize("user", [
    "all", "ALL", "All",            # every role on the cluster
    "", "   ",                      # no role at all
    "odoo, ci", 'od"oo',            # unquotable in a pg_hba field
    # pg_hba has THREE role-widening spellings, not one. `+role` means every
    # MEMBER of that role, transitively; `@file` means every role named in a file
    # this rule cannot read, so the set it authorises is unknowable. Both are
    # plausible values for a declared db_user - copied from a pg_hba example, or a
    # group-role setup - and both make the module's stated contract false.
    "+odoo", "+ODOO", "@/tmp/roles", "@roles.txt",
])
def test_a_role_field_that_would_widen_the_rule_is_refused(user):
    """The role field must name ONE role. Every spelling that means "more than the
    role Odoo connects as" is refused, and so is anything unquotable."""
    with pytest.raises(MOD.Refused):
        MOD.insert_block(STOCK, user, ["172.30.0.1/32"])


@pytest.mark.parametrize("user,why", [
    ("+odoo", "member"),
    ("@/tmp/roles", "file"),
])
def test_a_widening_role_refusal_explains_what_it_would_have_authorised(user, why):
    """A refusal that does not say WHY reads as a bug in the tool. Each of these has
    a different consequence, so each names its own."""
    with pytest.raises(MOD.Refused) as excinfo:
        MOD.render_rule(user, "172.30.0.1/32")
    assert why in str(excinfo.value).lower(), (
        "the refusal must name what {u!r} would have authorised; got {m!r}".format(
            u=user, m=str(excinfo.value)))


@pytest.mark.parametrize("addr", [
    "172.30.0.0/16",     # a bridge subnet - would trust every other container
    "0.0.0.0/0",         # the internet
    "172.30.0.1",        # bare: to PostgreSQL this is a HOST NAME, not one host
    "localhost/32",      # a name, resolved server-side at connect time
    "::/0",
    "fd00::1/64",
    "172.30.0.1/x",
    "999.1.1.1/32",
    "",
    # Malformed literals that satisfy the character-class regex but that PostgreSQL
    # cannot parse. These do NOT fail closed: an unparseable address makes the whole
    # FILE unparseable, and the postmaster refuses to START on that - so the cluster
    # stays up until its next restart and then does not come back.
    "1:2:3:4:5:6:7:8:9:10:11/128",
    ":::::/128",
    "fd00:::1/128",
    "gggg::1/128",
    "012.1.1.1/32",
])
def test_an_address_that_would_widen_the_rule_is_refused(addr):
    with pytest.raises(MOD.Refused):
        MOD.insert_block(STOCK, "odoo", [addr])


def test_no_address_at_all_is_refused_rather_than_emitting_an_empty_block():
    with pytest.raises(MOD.Refused):
        MOD.insert_block(STOCK, "odoo", [])


def test_a_refused_call_emits_nothing_at_all():
    """A refusal must produce no text: a partially rendered block piped back into a
    cluster is how a malformed call becomes a broken pg_hba.conf."""
    proc = subprocess.run(
        [sys.executable, str(HBA_EDIT), "apply", "--user", "all",
         "--address", "172.30.0.1/32"],
        input=STOCK, capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 2
    assert proc.stdout == "", f"nothing may be emitted on a refusal; got {proc.stdout!r}"
    assert "REFUSED" in proc.stderr


# --------------------------------------------------------------------------- #
# Guard 15 - reversibility, exactly
# --------------------------------------------------------------------------- #
def test_revert_removes_the_block_and_restores_the_original_bytes():
    """The revert is the user's escape route, so it must be exact - not "close".
    Anything less means the plugin cannot promise to undo what it did."""
    applied = MOD.insert_block(STOCK, "odoo", ["172.30.0.1/32"])
    assert MOD.strip_block(applied) == STOCK


def test_revert_of_a_file_that_was_never_touched_changes_nothing():
    assert MOD.strip_block(STOCK) == STOCK


def test_revert_leaves_a_rule_a_human_added_outside_the_markers():
    """Only the delimited region is owned. A rule the user added elsewhere must
    survive a revert - the plugin removes its own line, not the user's."""
    applied = MOD.insert_block(STOCK, "odoo", ["172.30.0.1/32"])
    plus_human = applied.replace(
        "host all all all scram-sha-256",
        "host    all     reporting    10.9.9.9/32    md5\nhost all all all scram-sha-256")
    reverted = MOD.strip_block(plus_human)
    assert "reporting" in reverted
    assert MOD.MANAGED_BEGIN not in reverted


def test_an_unterminated_managed_block_is_refused_not_guessed_at():
    """A BEGIN with no END is a corrupted file. Dropping to end-of-file would
    delete every rule a human appended after it; dropping one line would leave a
    live marker. Refuse and name the line, so the backup is used instead."""
    broken = STOCK.replace("local   all", MOD.MANAGED_BEGIN + "\nlocal   all", 1)
    with pytest.raises(MOD.Refused) as exc:
        MOD.strip_block(broken)
    assert MOD.MANAGED_END in str(exc.value)


# --------------------------------------------------------------------------- #
# The CLI contract, exercised the way the step exercises it
# --------------------------------------------------------------------------- #
def _run_cli(*args, stdin=None):
    return subprocess.run(
        [sys.executable, str(HBA_EDIT), *args],
        input=stdin, capture_output=True, text=True, timeout=30,
    )


def test_cli_round_trips_through_stdin_with_no_postgres_and_no_privilege(tmp_path):
    """The step pipes the file out of the cluster, through this filter, and back in.
    That whole path must work as a pure text filter, or the transform could only be
    tested by editing a live cluster."""
    applied = _run_cli("apply", "--user", "odoo", "--address", "172.30.0.1/32",
                       stdin=STOCK)
    assert applied.returncode == 0, applied.stderr
    reverted = _run_cli("revert", stdin=applied.stdout)
    assert reverted.returncode == 0, reverted.stderr
    assert reverted.stdout == STOCK


def test_cli_never_modifies_the_input_file_in_place(tmp_path):
    """`--file` is an INPUT. The privileged step owns where the result lands (an
    atomic same-directory rename inside the cluster), so this must not write."""
    src = tmp_path / "pg_hba.conf"
    src.write_text(STOCK, encoding="utf-8")
    before = src.read_bytes()
    proc = _run_cli("apply", "--user", "odoo", "--address", "172.30.0.1/32",
                    "--file", str(src))
    assert proc.returncode == 0, proc.stderr
    assert src.read_bytes() == before, "the input file was modified in place"
    assert MOD.MANAGED_BEGIN in proc.stdout


def test_cli_render_emits_only_the_block_for_the_advise_only_arm():
    """The native arm never edits a system file, so it needs the block alone to
    hand a human - and that text must come from the same renderer the docker arm
    writes, never from a second copy in prose."""
    proc = _run_cli("render", "--user", "odoo", "--address", "127.0.0.1/32")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines()[0] == MOD.MANAGED_BEGIN
    assert _fields(_managed_lines(proc.stdout)[0])["method"] == "trust"


@pytest.mark.parametrize("argv", [
    ("apply", "--user", "odoo"),                       # no address
    ("apply", "--address", "172.30.0.1/32"),           # no role
    ("apply", "--user", "odoo", "--allow-sudo"),       # a flag that must not exist
    ("frobnicate",),
])
def test_cli_refuses_an_unusable_invocation_without_emitting_a_rule(argv):
    proc = _run_cli(*argv, stdin=STOCK)
    assert proc.returncode == 2
    assert MOD.MANAGED_BEGIN not in proc.stdout


# --------------------------------------------------------------------------- #
# Structural guard: the escalation path the owner rejected must not exist
# --------------------------------------------------------------------------- #
def test_no_allow_sudo_escape_hatch_exists_anywhere_in_the_plugin():
    """The native arm is ADVISE-ONLY, with no opt-in that changes that.

    An `--allow-sudo` would ship privileged edits of a system file through a code
    path no observation covers - the arm was designed against a host that has no
    native cluster to exercise it on. Scanned across the whole plugin tree so the
    guard cannot pass by looking at one file.
    """
    offenders = []
    for path in list((PLUGIN).rglob("*.sh")) + list((PLUGIN).rglob("*.py")) \
            + list((PLUGIN).rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if re.search(r"--allow[-_]sudo", text):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, (
        f"a sudo escalation flag appears in: {offenders} - the native arm advises, "
        "it never edits a system file"
    )


def test_the_transform_needs_no_postgres_no_docker_and_no_privilege():
    """Stated as a test so it stays true: the module must import and transform with
    every external tool made unreachable. This is the property that lets the rule's
    narrowness be verified in CI, with no daemon and no cluster."""
    env = dict(os.environ)
    env["PATH"] = str(Path(shutil.which(sys.executable)).parent)
    proc = subprocess.run(
        [sys.executable, str(HBA_EDIT), "apply", "--user", "odoo",
         "--address", "172.30.0.1/32"],
        input=STOCK, capture_output=True, text=True, env=env, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    assert _fields(_managed_lines(proc.stdout)[0])["user"] == "odoo"
