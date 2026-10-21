#!/usr/bin/env python3
"""docs_site_config.py - read, propose and record the machine-global docs-sites.toml.

`docs-sites.toml` sits in the state root next to instances.toml (Tier-1: machine-global, never
committed; see snippets/state-root-resolution.md). Each `[[site]]` row declares one product
documentation repository for the odoo-doc-site skill:

    [[site]]
    key = "<short id>"
    remote = "<upstream remote URL identifying the docs repo>"
    fork_remote = "<git remote name feature branches are pushed to>"
    languages = ["<source>", "<target>", ...]       # source language first
    audience = "<who reads the site>"
    repos = ["<owner/repo or origin URL>", ...]     # optional: the code repos the site documents
    [site.series."<X.Y>"]
    clone = "<absolute path of a local clone>"      # at least one series declares one
    instance = "<instances.toml instance key>"      # the capture instance
    extra_modules = ["..."]                         # optional
    module_bridge_patterns = ["<prefix>{module}"]   # optional
    [site.policy]
    banned_terms = [...]  banned_terms_exempt_paths = [...]  forbid_version_prose = true
    marketplace_url = "https://.../{series}/{module}"  site_url_prefix = "https://.../"
    demo_company = { <lang> = "..." }  commit = "one-per-pr"|"per-area"
    check_shot = "first-per-series"|"always"  semantic_classes = [...]
    forward_port_branch_pattern = "<text>{series}<text>{pr}"   # optional; absent = no bot

A row declares at least one `clone` (any series): a worktree of any series is made from any clone
of the docs repo.

Subcommands (stdlib only; tomllib when present, else the reader of the TOML subset this file
writes, so the script runs on every python3 the plugin supports):

  check [--instances FILE]
      Exit 0 when at least one row is declared and every row is complete and valid; 1 otherwise,
      naming each problem (no file: one line naming the remedy); 2 when the file is unreadable.
  propose --repo PATH [--key K] [--instances FILE]
      READ-ONLY. KEY=VALUE facts derived from the clone at PATH (origin URL, fork candidates, the fork
      owners known from the catalog's clones when this clone has no pushed fork,
      series branches, languages, sibling clones per series, candidate catalog instances per
      series) and POLICY_FIELDS_TO_CONFIRM - the fields only the operator can state.
  record --key K --from-json FILE [--instances FILE]
      Validate the operator-confirmed row in FILE and upsert it as the ONE row of key K. The row
      is replaced whole; every other row and every comment outside it is kept byte for byte.
      Atomic write, backup first. Refuses unknown keys, an instance the catalog does not declare,
      a marketplace_url without {series} and {module}, and a row that `check` would call
      incomplete. Nothing is written on a refusal.
  show [--key K]
      The row (with --key) or every row as JSON.

Every path of a refusal exits non-zero and names the file or field. No secret is ever stored: a
remote URL that carries a password is refused.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import auto_mode_facts  # noqa: E402  (git readers)
import fork_facts  # noqa: E402  (the push-evidence rule and the fork status, one home)
import config_merge  # noqa: E402  (atomic replace, backup, lock, TOML string quoting)
import instances_io  # noqa: E402
import paths  # noqa: E402

try:
    import tomllib
except ImportError:  # python3 < 3.11: _loads reads the subset this file writes
    tomllib = None

FILE_NAME = "docs-sites.toml"
SERIES_RE = re.compile(r"^\d+\.\d+$")
SERIES_BRANCH_RE = re.compile(r"^\d+\.0$")
KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
REMOTE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
LANG_RE = re.compile(r"^[A-Za-z]{2,3}(?:[_-][A-Za-z0-9]+)*$")
MODULE_RE = re.compile(r"^[A-Za-z0-9_]+$")
BARE_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")
URL_RE = re.compile(r"^https?://\S+$")
# A code repo a site documents: owner/repo, a URL, or an scp-style git address.
REPO_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
REPO_URL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://\S+$")
REPO_SCP_RE = re.compile(r"^[A-Za-z0-9_.-]+@[A-Za-z0-9.-]+:\S+$")
URL_USERINFO_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*)://([^/@\s]*)@")
PLACEHOLDER_RE = re.compile(r"\{([^{}]*)\}")
# scheme://user:password@host - a stored credential.
URL_PASSWORD_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://[^/@\s]*:[^/@\s]*@")

SITE_KEYS = ("key", "remote", "fork_remote", "languages", "audience", "repos", "series", "policy")
SERIES_KEYS = ("clone", "instance", "extra_modules", "module_bridge_patterns")
POLICY_KEYS = ("banned_terms", "banned_terms_exempt_paths", "forbid_version_prose",
               "marketplace_url", "site_url_prefix", "demo_company", "commit", "check_shot",
               "semantic_classes", "forward_port_branch_pattern")
# Policy a row must state (an empty list is a confirmed "none"); the rest is optional, absent = off.
POLICY_REQUIRED = ("banned_terms", "forbid_version_prose", "commit", "check_shot")
COMMIT_CHOICES = ("one-per-pr", "per-area")
CHECK_SHOT_CHOICES = ("first-per-series", "always")
# Fields only the operator can state; propose lists them, never fills them.
POLICY_FIELDS_TO_CONFIRM = ("audience", "repos", "banned_terms", "banned_terms_exempt_paths",
                            "forbid_version_prose", "marketplace_url", "site_url_prefix",
                            "demo_company", "commit", "check_shot", "semantic_classes",
                            "forward_port_branch_pattern", "extra_modules",
                            "module_bridge_patterns")
FACTS_TO_CONFIRM = ("languages", "fork_remote", "series.clone", "series.instance",
                    "policy.forward_port_branch_pattern")


# --------------------------------------------------------------------------- paths

def sites_path():
    return os.path.join(paths.state_root(), FILE_NAME)


_BARE_RE = re.compile(r"[A-Za-z0-9_-]+")
_INT_RE = re.compile(r"[+-]?\d+(?:_\d+)*")
_ESCAPES = {"b": "\b", "t": "\t", "n": "\n", "f": "\f", "r": "\r", '"': '"', "\\": "\\"}


def _loads_subset(text):
    """Parse the TOML subset `render_row` writes, for a python3 without tomllib: `[[site]]` and
    dotted `[a.b."c"]` headers; `key = value` with a basic or literal string, a boolean, an
    integer, an array (several lines, comments inside) or a one-line inline table of those.
    Anything else - dotted keys, multi-line strings, floats, dates - is a ValueError, never a
    silent misread."""
    n = len(text)
    pos = 0

    def fail(message):
        raise ValueError("line %d: %s" % (text.count("\n", 0, pos) + 1, message))

    def skip(newlines):
        nonlocal pos
        while pos < n:
            c = text[pos]
            if c == "#":
                while pos < n and text[pos] != "\n":
                    pos += 1
            elif c in " \t\r" or (newlines and c == "\n"):
                pos += 1
            else:
                break

    def end_of_line():
        skip(False)
        if pos < n and text[pos] != "\n":
            fail("unexpected text after a value or header")

    def key_part():
        nonlocal pos
        if pos < n and text[pos] in "\"'":
            return string()
        m = _BARE_RE.match(text, pos)
        if not m:
            fail("expected a key")
        pos = m.end()
        return m.group(0)

    def string():
        nonlocal pos
        quote = text[pos]
        if text.startswith(quote * 3, pos):
            fail("multi-line strings are not supported")
        pos += 1
        out = []
        while True:
            if pos >= n or text[pos] == "\n":
                fail("unterminated string")
            c = text[pos]
            if c == quote:
                pos += 1
                return "".join(out)
            if quote == '"' and c == "\\":
                esc = text[pos + 1:pos + 2]
                if esc in _ESCAPES:
                    out.append(_ESCAPES[esc])
                    pos += 2
                    continue
                width = {"u": 4, "U": 8}.get(esc)
                digits = text[pos + 2:pos + 2 + (width or 0)]
                if not width or len(digits) != width or not re.fullmatch(r"[0-9A-Fa-f]+", digits):
                    fail("bad escape in a string")
                try:
                    out.append(chr(int(digits, 16)))
                except ValueError:
                    fail("bad escape in a string")
                pos += 2 + width
                continue
            if ord(c) < 0x20 and c != "\t":
                fail("control character in a string")
            out.append(c)
            pos += 1

    def value():
        nonlocal pos
        c = text[pos:pos + 1]
        if c in ('"', "'"):
            return string()
        if c == "[":
            pos += 1
            items = []
            while True:
                skip(True)
                if text[pos:pos + 1] == "]":
                    pos += 1
                    return items
                items.append(value())
                skip(True)
                if text[pos:pos + 1] == ",":
                    pos += 1
                elif text[pos:pos + 1] != "]":
                    fail("expected , or ] in an array")
        if c == "{":
            pos += 1
            table = {}
            skip(False)
            if text[pos:pos + 1] == "}":
                pos += 1
                return table
            while True:
                skip(False)
                name = key_part()
                skip(False)
                if text[pos:pos + 1] != "=":
                    fail("expected = in an inline table")
                pos += 1
                skip(False)
                if name in table:
                    fail("duplicate key %r" % name)
                table[name] = value()
                skip(False)
                if text[pos:pos + 1] == ",":
                    pos += 1
                elif text[pos:pos + 1] == "}":
                    pos += 1
                    return table
                else:
                    fail("expected , or } in an inline table")
        for word, result in (("true", True), ("false", False)):
            if text.startswith(word, pos):
                pos += len(word)
                return result
        m = _INT_RE.match(text, pos)
        if m and not re.match(r"[.eE:\-]", text[m.end():m.end() + 1]):
            pos = m.end()
            return int(m.group(0).replace("_", ""))
        fail("unsupported value")

    root = {}
    current = root
    while True:
        skip(True)
        if pos >= n:
            return root
        if text[pos] == "[":
            array = text.startswith("[[", pos)
            pos += 2 if array else 1
            parts = []
            while True:
                skip(False)
                parts.append(key_part())
                skip(False)
                if text[pos:pos + 1] == ".":
                    pos += 1
                else:
                    break
            closing = "]]" if array else "]"
            if not text.startswith(closing, pos):
                fail("expected %s" % closing)
            pos += len(closing)
            end_of_line()
            table = root
            for idx, part in enumerate(parts):
                last = idx == len(parts) - 1
                found = table.get(part)
                if last and array:
                    if found is None:
                        found = table[part] = []
                    if not isinstance(found, list):
                        fail("%r is not an array of tables" % part)
                    current = {}
                    found.append(current)
                    continue
                if found is None:
                    found = table[part] = {}
                if isinstance(found, list) and found:
                    found = found[-1]
                if not isinstance(found, dict):
                    fail("%r is not a table" % part)
                table = found
                if last:
                    current = found
            continue
        name = key_part()
        skip(False)
        if text[pos:pos + 1] != "=":
            fail("expected = after a key (dotted keys are not supported)")
        pos += 1
        skip(False)
        if name in current:
            fail("duplicate key %r" % name)
        current[name] = value()
        end_of_line()


def _loads(text):
    """The parsed TOML: tomllib when this python has it, else `_loads_subset`. ValueError on a
    file that does not parse."""
    return tomllib.loads(text) if tomllib is not None else _loads_subset(text)


def read_sites(path):
    """The parsed file as a dict. FileNotFoundError when absent; ValueError when unparseable."""
    with open(path, "rb") as fh:
        return _loads(fh.read().decode("utf-8"))


def site_rows(data):
    rows = data.get("site", [])
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def catalog_instances(instances_file):
    """{instance_key: series} of the catalog; {} when the catalog does not exist."""
    path = instances_file or auto_mode_facts._catalog_path()
    try:
        items = instances_io.load_instances(path)
    except FileNotFoundError:
        return {}
    return {instances_io.instance_key_of(it): instances_io.series_of(it) for it in items}


# --------------------------------------------------------------------------- validation

def _is_str(value):
    return isinstance(value, str) and value.strip() != "" and not re.search(r"[\x00-\x1f\x7f]", value)


def _str_list(value, label, problems, item_ok=None, item_hint="a non-empty string"):
    if not isinstance(value, list):
        problems.append("%s must be a list of strings" % label)
        return []
    out = []
    for item in value:
        if not _is_str(item) or (item_ok and not item_ok(item)):
            problems.append("%s: %r is not %s" % (label, item, item_hint))
        else:
            out.append(item)
    return out


def _repo_identifier_problem(value):
    """Why `value` is not a code-repo identifier (owner/repo, a URL, an scp-style address), or None.
    A credential in it - a password, or any userinfo on an http(s) URL - is refused."""
    if not _is_str(value) or re.search(r"\s", value):
        return "is not a repository identifier"
    m = URL_USERINFO_RE.match(value)
    if m and (m.group(1).lower().startswith("http") or ":" in m.group(2)):
        return "carries a credential; store the identifier without it"
    if REPO_URL_RE.match(value) or REPO_SCP_RE.match(value) or REPO_SLUG_RE.match(value):
        return None
    return "is not owner/repo or a repository URL"


def _placeholders_ok(text, allowed, required):
    names = set(PLACEHOLDER_RE.findall(text))
    return names <= set(allowed) and set(required) <= names


def _placeholders_exact(text, names):
    found = PLACEHOLDER_RE.findall(text)
    return set(found) == set(names) and len(found) == len(names)


def _unknown(mapping, allowed, label, problems):
    for name in mapping:
        if name not in allowed:
            problems.append("%s: unknown key %r (allowed: %s)" % (label, name, ", ".join(allowed)))


def validate_row(row, instances):
    """Problems of one site row (a list of strings; empty = complete and valid).

    `instances` is {instance_key: series} of the catalog: a series' `instance` must be one of its
    keys and belong to that series."""
    problems = []
    if not isinstance(row, dict):
        return ["the row must be an object"]
    _unknown(row, SITE_KEYS, "site", problems)

    key = row.get("key")
    if not isinstance(key, str) or not KEY_RE.match(key):
        problems.append("key must match %s" % KEY_RE.pattern)
    remote = row.get("remote")
    if not _is_str(remote) or re.search(r"\s", remote):
        problems.append("remote must be the upstream URL of the docs repo")
    elif URL_PASSWORD_RE.match(remote):
        problems.append("remote carries a password; store the URL without credentials")
    fork = row.get("fork_remote")
    if not isinstance(fork, str) or not REMOTE_NAME_RE.match(fork):
        problems.append("fork_remote must be a git remote name (letters, digits, . _ -)")

    langs = row.get("languages")
    if not isinstance(langs, list) or not langs:
        problems.append("languages must list at least the source language")
    else:
        for lang in langs:
            if not isinstance(lang, str) or not LANG_RE.match(lang):
                problems.append("languages: %r is not a language code" % (lang,))
        if len(set(map(str, langs))) != len(langs):
            problems.append("languages must not repeat a language")
    if not _is_str(row.get("audience")):
        problems.append("audience must state who reads the site")
    if "repos" in row:
        repos = row["repos"]
        if not isinstance(repos, list) or not repos:
            problems.append("repos must be a non-empty list of repository identifiers "
                            "(leave it out when the operator names none)")
        else:
            for item in repos:
                why = _repo_identifier_problem(item)
                if why:
                    problems.append("repos: %r %s" % (item, why))
            if len(set(map(str, repos))) != len(repos):
                problems.append("repos must not repeat a repository")

    series = row.get("series")
    if not isinstance(series, dict) or not series:
        problems.append("series must declare at least one series with its capture instance")
    else:
        for name, entry in series.items():
            label = "series.%s" % name
            if not SERIES_RE.match(str(name)):
                problems.append("%s: the series name must look like X.Y" % label)
            if not isinstance(entry, dict):
                problems.append("%s must be a table" % label)
                continue
            _unknown(entry, SERIES_KEYS, label, problems)
            clone = entry.get("clone")
            if clone is not None and (not _is_str(clone) or not os.path.isabs(clone)):
                problems.append("%s.clone must be an absolute path" % label)
            elif clone is not None and not os.path.isdir(clone):
                problems.append("%s.clone: %s is not a directory" % (label, clone))
            inst = entry.get("instance")
            if not _is_str(inst):
                problems.append("%s.instance must name the capture instance (an instances.toml key)" % label)
            elif inst not in instances:
                problems.append("%s.instance: %r is not declared in the instance catalog "
                                "(declared: %s)" % (label, inst, ", ".join(sorted(instances)) or "none"))
            elif instances[inst] != str(name):
                problems.append("%s.instance: %r is a series %s instance" % (label, inst, instances[inst]))
            if "extra_modules" in entry:
                _str_list(entry["extra_modules"], label + ".extra_modules", problems,
                          MODULE_RE.match, "an Odoo module name")
            if "module_bridge_patterns" in entry:
                _str_list(entry["module_bridge_patterns"], label + ".module_bridge_patterns",
                          problems, lambda p: _placeholders_ok(p, ("module",), ("module",)),
                          "a pattern naming {module}")

    if isinstance(series, dict) and series and not any(
            isinstance(e, dict) and e.get("clone") is not None for e in series.values()):
        problems.append("series: at least one series must declare a clone (the local checkout of "
                        "the docs repo a worktree of any series is made from)")

    policy = row.get("policy")
    if not isinstance(policy, dict):
        problems.append("policy must be declared (a table; see POLICY_FIELDS_TO_CONFIRM)")
        return problems
    _unknown(policy, POLICY_KEYS, "policy", problems)
    for name in POLICY_REQUIRED:
        if name not in policy:
            problems.append("policy.%s must be confirmed by the operator" % name)
    for name in ("banned_terms", "banned_terms_exempt_paths", "semantic_classes"):
        if name in policy:
            hint = "a non-empty string"
            ok = None
            if name == "banned_terms_exempt_paths":
                ok = lambda p: not p.startswith("/") and ".." not in p.split("/")  # noqa: E731
                hint = "a path relative to the docs repo"
            _str_list(policy[name], "policy." + name, problems, ok, hint)
    if "forbid_version_prose" in policy and not isinstance(policy["forbid_version_prose"], bool):
        problems.append("policy.forbid_version_prose must be true or false")
    market = policy.get("marketplace_url")
    if market is not None and not (_is_str(market) and URL_RE.match(market)
                                   and _placeholders_ok(market, ("series", "module"), ("series", "module"))):
        problems.append("policy.marketplace_url must be an http(s) URL naming both {series} and {module}")
    prefix = policy.get("site_url_prefix")
    if prefix is not None and not (_is_str(prefix) and URL_RE.match(prefix) and "{" not in prefix):
        problems.append("policy.site_url_prefix must be an http(s) URL")
    demo = policy.get("demo_company")
    if demo is not None:
        if not isinstance(demo, dict):
            problems.append("policy.demo_company must map a language to a company name")
        else:
            known = set(langs) if isinstance(langs, list) else set()
            for lang, name in demo.items():
                if lang not in known:
                    problems.append("policy.demo_company: %r is not one of the site languages" % lang)
                if not _is_str(name):
                    problems.append("policy.demo_company.%s must be a company name" % lang)
    fp = policy.get("forward_port_branch_pattern")
    if fp is not None and not (_is_str(fp) and not re.search(r"\s", fp)
                               and _placeholders_exact(fp, ("pr", "series"))):
        problems.append("policy.forward_port_branch_pattern must be a branch-name pattern naming "
                        "{pr} and {series} and no other placeholder (leave it unset when the "
                        "docs repo has no forward-port bot)")
    if "commit" in policy and policy["commit"] not in COMMIT_CHOICES:
        problems.append("policy.commit must be one of: %s" % ", ".join(COMMIT_CHOICES))
    if "check_shot" in policy and policy["check_shot"] not in CHECK_SHOT_CHOICES:
        problems.append("policy.check_shot must be one of: %s" % ", ".join(CHECK_SHOT_CHOICES))
    return problems


# --------------------------------------------------------------------------- rendering

def _q(value):
    return config_merge._toml_basic_string(value)


def _arr(values):
    return "[%s]" % ", ".join(_q(v) for v in values)


def _tkey(name):
    return name if BARE_KEY_RE.match(name) else _q(name)


def render_row(row):
    """TOML text of one validated row (no trailing blank line)."""
    out = ["[[site]]",
           "key = %s" % _q(row["key"]),
           "remote = %s" % _q(row["remote"]),
           "fork_remote = %s" % _q(row["fork_remote"]),
           "languages = %s" % _arr(row["languages"]),
           "audience = %s" % _q(row["audience"])]
    if "repos" in row:
        out.append("repos = %s" % _arr(row["repos"]))
    for name in sorted(row["series"], key=instances_io._series_key):
        entry = row["series"][name]
        out += ["", "[site.series.%s]" % _q(name)]
        if "clone" in entry:
            out.append("clone = %s" % _q(entry["clone"]))
        out.append("instance = %s" % _q(entry["instance"]))
        for opt in ("extra_modules", "module_bridge_patterns"):
            if opt in entry:
                out.append("%s = %s" % (opt, _arr(entry[opt])))
    policy = row["policy"]
    out += ["", "[site.policy]"]
    for name in POLICY_KEYS:
        if name not in policy:
            continue
        value = policy[name]
        if isinstance(value, bool):
            out.append("%s = %s" % (name, "true" if value else "false"))
        elif isinstance(value, list):
            out.append("%s = %s" % (name, _arr(value)))
        elif isinstance(value, dict):
            out.append("%s = { %s }" % (name, ", ".join("%s = %s" % (_tkey(k), _q(v))
                                                        for k, v in value.items())))
        else:
            out.append("%s = %s" % (name, _q(value)))
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- text upsert

_HEADER_RE = re.compile(r"^\s*(\[\[?)\s*([A-Za-z0-9_\"'.\- ]+?)\s*\]\]?\s*(?:#.*)?$")


def _row_blocks(lines):
    """[(first, last)] line spans of each [[site]] row, sub-tables included. A row ends before the
    next header that is not one of its own sub-tables; trailing blank and comment lines belong to
    the gap after it, so a comment that heads the next row stays with that row."""
    blocks, start, idx = [], None, 0
    while idx < len(lines):
        stripped = lines[idx].strip()
        header = _HEADER_RE.match(lines[idx]) if stripped.startswith("[") else None
        if header:
            is_site = header.group(1) == "[[" and header.group(2).replace(" ", "") == "site"
            own = header.group(2).replace(" ", "").startswith("site.")
            if is_site:
                if start is not None:
                    blocks.append((start, idx - 1))
                start = idx
            elif not own and start is not None:
                blocks.append((start, idx - 1))
                start = None
            idx += 1
            continue
        if "=" in stripped and not stripped.startswith("#"):
            idx = config_merge._toml_value_span(lines, idx) + 1
            continue
        idx += 1
    if start is not None:
        blocks.append((start, len(lines) - 1))
    trimmed = []
    for first, last in blocks:
        while last > first and (not lines[last].strip() or lines[last].lstrip().startswith("#")):
            last -= 1
        trimmed.append((first, last))
    return trimmed


def upsert_text(text, row):
    """(new_text, replaced) - `row` replaces the [[site]] block of its key, else is appended."""
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    new = render_row(row).splitlines(keepends=True)
    for first, last in _row_blocks(lines):
        parsed = _loads("".join(lines[first:last + 1]))
        if site_rows(parsed) and site_rows(parsed)[0].get("key") == row["key"]:
            return "".join(lines[:first] + new + lines[last + 1:]), True
    if lines and lines[-1].strip():
        lines.append("\n")
    return "".join(lines + new), False


# --------------------------------------------------------------------------- subcommands

def _fail(message, code=1):
    print("x " + message, file=sys.stderr)
    return code


def _load_or_report(path):
    try:
        return read_sites(path), 0
    except FileNotFoundError:
        return None, 1
    except (OSError, ValueError) as exc:
        print("x %s could not be read as TOML: %s" % (path, exc), file=sys.stderr)
        return None, 2


def cmd_check(args):
    path = sites_path()
    data, status = _load_or_report(path)
    if status == 2:
        return 2
    if data is None:
        return _fail("no docs site is declared (no %s) - run /odoo-ai-agents:odoo-setup docs-site" % path)
    rows = site_rows(data)
    if not rows:
        return _fail("%s declares no [[site]] row - run /odoo-ai-agents:odoo-setup docs-site" % path)
    try:
        instances = catalog_instances(args.instances)
    except (OSError, ValueError) as exc:
        return _fail("the instance catalog could not be read: %s" % exc, 2)
    bad = 0
    seen = {}
    for idx, row in enumerate(rows, 1):
        label = row.get("key") if isinstance(row.get("key"), str) else "#%d" % idx
        problems = validate_row(row, instances)
        if label in seen:
            problems.append("key %r is declared twice" % label)
        seen[label] = True
        for problem in problems:
            print("  site %s: %s" % (label, problem))
        bad += bool(problems)
    return 1 if bad else 0


def _emit(name, value):
    if isinstance(value, (list, tuple)):
        value = ",".join(value)
    print("%s=%s" % (name, shlex.quote(str(value))))


def _public_url(url):
    """The remote URL without credentials: an http(s) userinfo is dropped, as is any ssh password."""
    m = re.match(r"^([A-Za-z][A-Za-z0-9+.-]*://)([^/@]*)@(.*)$", url)
    if not m:
        return url
    scheme, userinfo, rest = m.groups()
    if scheme.lower().startswith("http") or ":" in userinfo:
        return scheme + rest
    return url


def _canon(url):
    """host/path of a remote URL, lower-case host, no credentials, no .git - to compare two clones."""
    u = url.strip()
    m = re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://(?:[^@/]*@)?([^/:]+)(?::\d+)?/(.*)$", u)
    if not m:
        m = re.match(r"^(?:[^@/:]+@)?([^/:]+):(.*)$", u)
    if not m:
        return u.rstrip("/")
    path = m.group(2).strip("/")
    path = path[:-4] if path.endswith(".git") else path
    return m.group(1).lower() + "/" + path


def _series_sort(names):
    return sorted(set(names), key=instances_io._series_key)


def _origin_series_branches(repo):
    refs = auto_mode_facts._git(repo, "for-each-ref", "--format=%(refname)", "refs/remotes/origin")
    prefix = "refs/remotes/origin/"
    return [r[len(prefix):] for r in refs.splitlines()
            if r.startswith(prefix) and SERIES_BRANCH_RE.match(r[len(prefix):])]


_SERIES_TOKEN = re.compile(r"(?<![\d.])\d+\.\d+(?![\d.])")


def _forward_port_candidate(branches):
    """(pattern, evidence) when at least two origin branches share the shape <text><series>
    <text><pr number><text> (one series token, one other number); ("", []) otherwise."""
    shapes = {}
    for name in branches:
        if "{" in name or "}" in name:
            continue
        tokens = _SERIES_TOKEN.findall(name)
        if len(tokens) != 1:
            continue
        masked = _SERIES_TOKEN.sub("\0S\0", name)
        numbers = re.findall(r"\d+", masked)
        if len(numbers) != 1:
            continue
        shape = re.sub(r"\d+", "{pr}", masked).replace("\0S\0", "{series}")
        shapes.setdefault(shape, []).append(name)
    if not shapes:
        return "", []
    shape, names = max(sorted(shapes.items()), key=lambda kv: len(kv[1]))
    if len(names) < 2 or not _placeholders_exact(shape, ("pr", "series")):
        return "", []
    return shape, sorted(names)[:3]


def _origin_branches(repo):
    refs = auto_mode_facts._git(repo, "for-each-ref", "--format=%(refname)", "refs/remotes/origin")
    prefix = "refs/remotes/origin/"
    return [r[len(prefix):] for r in refs.splitlines() if r.startswith(prefix)]


def _languages(root):
    """(languages in the order the docs repo states them, the per-source facts)."""
    try:
        from docs_site import repo_facts
        langs = repo_facts.collect(root).get("languages", {})
    except Exception:  # a reader that cannot parse the repo leaves the fact UNKNOWN, never guessed
        return [], {}
    facts = {"makefile": langs.get("makefile") or [],
             "conf": langs.get("conf_supported_languages") or [],
             "locale": langs.get("locale_dirs") or []}
    for source in ("makefile", "conf", "locale"):
        if facts[source]:
            return list(facts[source]), facts
    return [], facts


def _sibling_clones(root, origin_canon):
    """{series: [absolute path]} of principal clones of the same repo checked out on a series branch."""
    found = {}
    parent = os.path.dirname(root)
    candidates = [root]
    try:
        candidates += [os.path.join(parent, n) for n in sorted(os.listdir(parent))]
    except OSError:
        pass
    seen = set()
    for cand in candidates:
        real = os.path.realpath(cand)
        if real in seen or not os.path.isdir(os.path.join(real, ".git")):
            continue  # a linked worktree has a .git FILE and is not a principal clone
        seen.add(real)
        url = auto_mode_facts._git(real, "remote", "get-url", "origin")
        if not url or _canon(url) != origin_canon:
            continue
        branch = auto_mode_facts._git(real, "symbolic-ref", "--short", "HEAD")
        if SERIES_BRANCH_RE.match(branch):
            found.setdefault(branch, []).append(real)
    return found


def cmd_propose(args):
    root = auto_mode_facts._git_root(args.repo) if os.path.isdir(args.repo) else ""
    if not root:
        return _fail("%s is not inside a git clone - pass the local clone of the docs repo" % args.repo)
    origin = auto_mode_facts._git(root, "remote", "get-url", "origin")
    if not origin:
        return _fail("%s has no 'origin' remote - the docs repo is identified by its origin URL" % root)
    remotes = auto_mode_facts._git(root, "remote").split()
    head = auto_mode_facts._git(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    default = head[len("origin/"):] if head.startswith("origin/") else ""
    others = [r for r in remotes if r != "origin"]
    fork = fork_facts.fork_facts(root)
    pushed = {r["name"] for r in fork["remotes"] if r["pushed"]}
    key = args.key or re.sub(r"\.git$", "", os.path.basename(_canon(origin))) or os.path.basename(root)

    declared = 0
    try:
        data = read_sites(sites_path())
        declared = int(any(r.get("key") == key for r in site_rows(data)))
    except (OSError, ValueError):
        pass

    branches = _origin_series_branches(root)
    clones = _sibling_clones(root, _canon(origin))
    try:
        instances = catalog_instances(args.instances)
    except (OSError, ValueError):
        instances = {}
    series = _series_sort(branches + list(clones))
    languages, lang_facts = _languages(root)

    _emit("SITE_KEY", key)
    _emit("DECLARED", declared)
    _emit("REPO", root)
    _emit("REMOTE", _public_url(origin))
    _emit("REMOTES", remotes)
    _emit("REMOTE_URLS", ["%s=%s" % (r, _public_url(auto_mode_facts._git(root, "remote", "get-url", r)))
                          for r in remotes])
    _emit("FORK_CANDIDATES", [r for r in others if r in pushed])
    _emit("OTHER_REMOTES", [r for r in others if r not in pushed])
    for name, value in fork_facts.pairs(fork):
        _emit(name, value)
    if fork["status"] != fork_facts.PUSHED:
        known = fork_facts.known_owners(
            [fork] + [fork_facts.fork_facts(r) for r in auto_mode_facts.catalog_repos(args.instances)])
        if known:
            _emit("FORK_KNOWN_OWNERS", known)
    _emit("DEFAULT_BRANCH", default)
    _emit("SERIES", series)
    _emit("SERIES_BRANCHES_ON_ORIGIN", _series_sort(branches))
    _emit("LANGUAGES", languages if languages else "UNKNOWN")
    _emit("LANGUAGES_MAKEFILE", lang_facts.get("makefile", []))
    _emit("LANGUAGES_CONF", lang_facts.get("conf", []))
    _emit("LANGUAGES_LOCALE", lang_facts.get("locale", []))
    for name in series:
        tag = "SERIES_%s" % name.replace(".", "_")
        _emit(tag + "_CLONES", sorted(clones.get(name, [])))
        _emit(tag + "_INSTANCES", sorted(k for k, s in instances.items() if s == name))
    fp_pattern, fp_evidence = _forward_port_candidate(_origin_branches(root))
    _emit("FORWARD_PORT_BRANCH_PATTERN_CANDIDATE", fp_pattern)
    _emit("FORWARD_PORT_BRANCH_PATTERN_EVIDENCE", fp_evidence)
    _emit("FACTS_TO_CONFIRM", FACTS_TO_CONFIRM)
    _emit("POLICY_FIELDS_TO_CONFIRM", POLICY_FIELDS_TO_CONFIRM)
    return 0


def _read_json_row(path, key):
    try:
        with open(path, encoding="utf-8") as fh:
            row = json.load(fh)
    except (OSError, ValueError) as exc:
        raise ValueError("cannot read %s as JSON: %s" % (path, exc))
    if not isinstance(row, dict):
        raise ValueError("%s must hold one JSON object (the site row)" % path)
    if "key" in row and row["key"] != key:
        raise ValueError("--key %s does not match the row's key %r" % (key, row["key"]))
    row = dict(row)
    row["key"] = key
    return row


def cmd_record(args):
    try:
        row = _read_json_row(args.from_json, args.key)
        instances = catalog_instances(args.instances)
    except (OSError, ValueError) as exc:
        return _fail(str(exc) + " Nothing was recorded.", 2)
    problems = validate_row(row, instances)
    if problems:
        for problem in problems:
            print("x %s" % problem, file=sys.stderr)
        return _fail("the row is not valid. Nothing was recorded.", 2)

    path = sites_path()
    with config_merge.locked_target(path):
        try:
            with open(path, encoding="utf-8") as fh:
                old_text = fh.read()
            existed = True
        except FileNotFoundError:
            old_text, existed = "", False
        except OSError as exc:
            return _fail("cannot read %s: %s. Nothing was recorded." % (path, exc))
        try:
            old = _loads(old_text) if existed else {}
        except ValueError as exc:
            return _fail("%s is not valid TOML (%s). Fix it by hand and re-run. Nothing was recorded."
                         % (path, exc), 2)
        if sum(1 for r in site_rows(old) if r.get("key") == row["key"]) > 1:
            return _fail("%s declares key %r more than once. Remove the duplicate by hand. "
                         "Nothing was recorded." % (path, row["key"]), 2)
        new_text, replaced = upsert_text(old_text, row)
        # The published text must parse back to exactly: the other rows as they were, and this one.
        try:
            reparsed = _loads(new_text)
        except ValueError as exc:
            return _fail("internal: the rendered row does not parse (%s). Nothing was recorded." % exc, 2)
        expected = [r for r in site_rows(old) if r.get("key") != row["key"]]
        got = [r for r in site_rows(reparsed) if r.get("key") != row["key"]]
        mine = [r for r in site_rows(reparsed) if r.get("key") == row["key"]]
        if got != expected or len(mine) != 1 or mine[0] != row:
            return _fail("internal: the rendered file does not round-trip. Nothing was recorded.", 2)
        if new_text == old_text:
            print("  docs site %s unchanged" % row["key"])
            return 0
        directory = os.path.dirname(path)
        os.makedirs(directory, exist_ok=True)
        gitignore = os.path.join(directory, ".gitignore")
        if not os.path.exists(gitignore):
            with open(gitignore, "w", encoding="utf-8") as fh:
                fh.write("*\n")
        try:
            if existed:
                config_merge._backup(path)
            config_merge._atomic_replace(path, new_text)
        except OSError as exc:
            return _fail("cannot write %s: %s. Nothing was recorded." % (path, exc))
    print("  recorded docs site %s (%s) in %s" % (row["key"], "replaced" if replaced else "added", path))
    return 0


def cmd_show(args):
    path = sites_path()
    data, status = _load_or_report(path)
    if status == 2:
        return 2
    if data is None:
        return _fail("no docs site is declared (no %s) - run /odoo-ai-agents:odoo-setup docs-site" % path)
    rows = site_rows(data)
    if args.key:
        match = [r for r in rows if r.get("key") == args.key]
        if not match:
            return _fail("no docs site with key %r in %s (declared: %s)"
                         % (args.key, path, ", ".join(str(r.get("key")) for r in rows) or "none"))
        payload = match[0]
    else:
        payload = rows
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="docs_site_config.py", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check")
    p.add_argument("--instances")
    p = sub.add_parser("propose")
    p.add_argument("--repo", required=True)
    p.add_argument("--key")
    p.add_argument("--instances")
    p = sub.add_parser("record")
    p.add_argument("--key", required=True)
    p.add_argument("--from-json", required=True, dest="from_json")
    p.add_argument("--instances")
    p = sub.add_parser("show")
    p.add_argument("--key")
    args = parser.parse_args(argv)
    return {"check": cmd_check, "propose": cmd_propose, "record": cmd_record,
            "show": cmd_show}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
