"""odoo_source_facts.py - read Odoo build facts from a checkout's SOURCE TEXT.

Odoo facts (what a series itself declares) are read from the checkout, never
from a hand-kept table, so a new Odoo series needs no plugin edit. Deployment
facts (which addons a site loads server-wide) are proposed from the addons'
own code and from a probe build's log, then confirmed by the operator and kept
in the catalog row (`server_wide_modules`) - this module only PROPOSES them.

Every reader is text parsing: nothing here imports Odoo, and a checkout of any
series (Python 2 era included) is only read, never executed. Standard library
only; syntax stays Python 3.8 compatible because setup steps run it with
whatever interpreter the host has.

Public API (stable - other scripts import it):

  core_server_wide_modules(odoo_root) -> list[str] | None
      Odoo's own default server-wide set for that checkout: the `my_default`
      of the `--load` option in `odoo/tools/config.py` (`openerp/tools/config.py`
      on the series whose core package is `openerp/`), resolving a module
      constant such as `DEFAULT_SERVER_WIDE_MODULES` when the default names
      one. None when the file or the option cannot be read.

  cli_options(odoo_root) -> dict | None
      Every option the core package's `tools/config.py` adds:
      {"--long-name": {"short", "dest", "takes_value"}}. The readers below
      answer from it; None when config.py is unreadable.

  demo_opt_in(odoo_root) -> bool | None
      True when config.py declares `--with-demo` (demo data is off by default
      and opt-in), False when it declares only `--without-demo` (demo loads by
      default), None when unreadable or neither is declared.

  http_port_key(odoo_root) / second_port_key(odoo_root) -> str | None
      The dest (= odoo.conf key) of the main port option (`--http-port`, else
      `--xmlrpc-port`) and of the second port option (`--gevent-port`, else
      `--longpolling-port`). The odoo-bin flag is `--` + key with `_` as `-`.

  dev_takes_value(odoo_root) -> bool | None
      True when `--dev` takes a value (`--dev=all` is valid), False when it is
      a boolean flag or absent.

  short_options(odoo_root) -> dict | None
      {char: {"long", "takes_value"}} for every declared short option plus
      optparse's own -h; long names spelled with `-` for `_`.

  core_package(odoo_root) -> str | None
      `odoo`, or `openerp` on the oldest series: the core package holding
      release.py, which is also the root of Odoo's logger namespace.

  i18n_export_cli(odoo_root) -> dict | None
      Which command line exports one module's translation file, and how its
      options are spelled - the SERVER command where config.py declares
      `--i18n-export` with `--modules` and `--language`:
        {"form": "server", "export": "--i18n-export", "modules": "--modules",
         "language": "--language"}
      else the `i18n` SUBCOMMAND (`<core package>/cli/i18n.py`; the command is
      the module's name) whose `export` subparser declares `--output` and
      `--languages`, with `--config` and `--database` declared on it (its
      connection facts come from the config file only):
        {"form": "subcommand", "command": "i18n", "subcommand": "export",
         "config": "--config", "database": "--database", "output": "--output",
         "languages": "--languages"}
      None when neither is fully declared - never a guess.

  python_support(odoo_root) -> dict | None
      {"min": "3.10", "max": "3.14" | None, "source": <where it came from>}.
      Ordered, first hit wins:
        1. MIN_PY_VERSION / MAX_PY_VERSION in the core package's release.py or
           __init__.py                            -> source "release.py" / "__init__.py"
        2. setup.py `python_requires` (">=X.Y", optional "<=X.Y")
                                                   -> source "setup.py" (max None
                                                      when no upper bound)
        3. debian/control `X-Python-Version`       -> source "debian"
        4. a Python 2 shebang on odoo-bin / openerp-server (`python`, `python2`)
                                                   -> source "shebang", 2.7
      None when none of those yields a version.

  self_declared_server_wide(addons_paths) -> list[str]
      Modules in those addons directories whose own Python code tests their
      OWN technical name against the `server_wide_modules` config option
      (e.g. `if 'm' in config.get('server_wide_modules', '').split(',')`,
      `'m' in config_options.get('server_wide_modules', [])`,
      `'m' in odoo.conf.server_wide_modules`). Such a module only works fully
      when loaded with `--load`. Sorted, deduplicated. A module that merely
      DOCUMENTS the need in prose is not detected - the operator adds it.

  locate_odoo_root(odoo_root=None, addons_paths=None) -> str | None
      The Odoo checkout root to read facts from: the declared `odoo_root` when it
      holds a core package or a server launcher, else the first addons_path entry,
      its parent or its grandparent that does (a core `addons` dir sits in the checkout root,
      `odoo/addons` one level deeper). None when none does.

  locate_odoo_launcher(odoo_root=None, addons_paths=None) -> str | None
      The executable server launcher to run: `odoo-bin`, or `openerp-server` on the series
      whose core package is `openerp/` - found at the first of the same candidate roots
      locate_odoo_root walks that has one. core_launcher(root) answers for one root.

  python_recommendation(series, odoo_root=None, matrix_path=None) -> dict | None
      {"recommended", "min", "max", "source", "python2"} for building a venv.
      The range comes from python_support(odoo_root) whenever the checkout is
      readable - the fallback table (odoo-python-matrix.json next to this file)
      only fills in when it is not, with source "matrix". "recommended" is the
      table's editorial pick when it lies inside the source range, else the
      source minimum (a new series the table does not know needs no edit).

  server_wide_warning_modules(log_text) -> list[str]
      Module names from Odoo log lines of the shape
      "The module `m` should be loaded in server wide mode using `--load` ...".
      Sorted, deduplicated.

CLI (for shell setup steps; every fact prints as KEY=value on stdout):

  python3 odoo_source_facts.py core-load <odoo_root>
      CORE_SERVER_WIDE_MODULES=base,web            exit 0; exit 3 when unreadable
  python3 odoo_source_facts.py cli-facts <odoo_root>
      CORE_PACKAGE=odoo / DEMO_OPT_IN=1|0 (empty when undeclared) /
      WITHOUT_DEMO=1|0 (--without-demo declared) / HTTP_PORT_KEY=http_port / SECOND_PORT_KEY=gevent_port / DEV_TAKES_VALUE=1|0
                                                   exit 0; exit 3 when config.py is unreadable
  python3 odoo_source_facts.py i18n-facts <odoo_root>
      I18N_FORM=server + I18N_EXPORT_FLAG / I18N_MODULES_FLAG / I18N_LANGUAGE_FLAG, or
      I18N_FORM=subcommand + I18N_COMMAND / I18N_SUBCOMMAND / I18N_CONFIG_FLAG /
      I18N_DATABASE_FLAG / I18N_OUTPUT_FLAG / I18N_LANGUAGES_FLAG
                                                   exit 0; exit 3 when neither is declared
  python3 odoo_source_facts.py python <odoo_root>
      PY_MIN=3.10 / PY_MAX=3.14 (empty when open) / PY_SOURCE=release.py
                                                   exit 0; exit 3 when unreadable
  python3 odoo_source_facts.py python-suggest <series> [<odoo_root>]
      PY_RECOMMENDED / PY_MIN / PY_MAX / PY_SOURCE / PY_PYTHON2=0|1
                                                   exit 0; exit 3 when nothing is known
  python3 odoo_source_facts.py locate-root [--odoo-root <dir>] [<addons_dir> ...]
      ODOO_ROOT=/path/to/checkout                  exit 0; exit 3 when none holds Odoo
  python3 odoo_source_facts.py locate-launcher [--odoo-root <dir>] [<addons_dir> ...]
      ODOO_LAUNCHER=/path/odoo-bin + ODOO_ROOT=<its dir>  exit 0; exit 3 when none has one
  python3 odoo_source_facts.py self-declared <addons_dir> [<addons_dir> ...]
      SELF_DECLARED_SERVER_WIDE=to_base,viin_brand (empty when none) exit 0
  python3 odoo_source_facts.py warnings [<logfile> ...]   (stdin when no file)
      SERVER_WIDE_WARNINGS=viin_brand (empty when none)   exit 0
  Usage errors exit 2.
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys

__all__ = [
    "cli_options",
    "core_launcher",
    "core_package",
    "core_server_wide_modules",
    "demo_opt_in",
    "dev_takes_value",
    "http_port_key",
    "i18n_export_cli",
    "locate_odoo_launcher",
    "locate_odoo_root",
    "python_recommendation",
    "python_support",
    "second_port_key",
    "self_declared_server_wide",
    "server_wide_warning_modules",
    "short_options",
]

# The core package directory is `openerp/` on the oldest series and `odoo/`
# afterwards; both are probed, newest spelling first.
_CORE_PACKAGES = ("odoo", "openerp")

# Module descriptors: `__openerp__.py` on the oldest series, `__manifest__.py`
# afterwards. A directory holding either is an addon.
_DESCRIPTORS = ("__manifest__.py", "__openerp__.py")

# Directories inside an addon that never hold server-side Python worth scanning.
_SKIP_DIRS = frozenset(("static", "node_modules", "__pycache__", ".git", "i18n"))

# A single source file larger than this is not an addon module file; skipping it
# bounds the scan without losing any realistic self-check.
_MAX_SCAN_BYTES = 2 * 1024 * 1024

_OPTION_KEY = "server_wide_modules"


def _read_text(path: str) -> str | None:
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return None
    return raw.decode("utf-8", errors="replace")


def _balanced_span(text: str, start: int) -> int | None:
    """Return the index just past the bracket closing the one opened at or
    after `start`, skipping string literals. None when unbalanced."""
    pairs = {"(": ")", "[": "]", "{": "}"}
    stack = []
    i = start
    n = len(text)
    quote = None
    while i < n:
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if text.startswith(quote, i):
                i += len(quote)
                quote = None
                continue
            i += 1
            continue
        if ch in "'\"":
            quote = text[i:i + 3] if text[i:i + 3] in ("'''", '"""') else ch
            i += len(quote)
            continue
        if ch == "#":
            nl = text.find("\n", i)
            i = n if nl < 0 else nl
            continue
        if ch in pairs:
            stack.append(pairs[ch])
        elif stack and ch == stack[-1]:
            stack.pop()
            if not stack:
                return i + 1
        i += 1
    return None


def _expr_end(text: str, start: int) -> int:
    """End of a keyword-argument value starting at `start`: the first top-level
    `,` or unbalanced `)`, skipping nested brackets and strings."""
    i = start
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in "([{":
            end = _balanced_span(text, i)
            if end is None:
                return n
            i = end
            continue
        if ch in "'\"":
            quote = text[i:i + 3] if text[i:i + 3] in ("'''", '"""') else ch
            j = i + len(quote)
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text.startswith(quote, j):
                    j += len(quote)
                    break
                j += 1
            i = j
            continue
        if ch in ",)":
            return i
        i += 1
    return n


def _modules_from_value(value) -> list[str] | None:
    if isinstance(value, str):
        items = value.split(",")
    elif isinstance(value, (list, tuple)):
        if not all(isinstance(v, str) for v in value):
            return None
        items = list(value)
    else:
        return None
    return [m.strip() for m in items if m.strip()]


def _resolve_constant(text: str, name: str):
    m = re.search(r"^%s\s*=\s*" % re.escape(name), text, re.M)
    if not m:
        return None
    start = m.end()
    if start < len(text) and text[start] in "([{":
        end = _balanced_span(text, start)
        if end is None:
            return None
        expr = text[start:end]
    else:
        nl = text.find("\n", start)
        expr = text[start:] if nl < 0 else text[start:nl]
    try:
        return ast.literal_eval(expr.strip())
    except (ValueError, SyntaxError):
        return None


def core_server_wide_modules(odoo_root) -> list[str] | None:
    """Odoo's own default `--load` set for the checkout at `odoo_root`."""
    if not odoo_root:
        return None
    for pkg in _CORE_PACKAGES:
        text = _read_text(os.path.join(str(odoo_root), pkg, "tools", "config.py"))
        if text is None:
            continue
        opt = re.search(r"""add_option\(\s*['"]--load['"]""", text)
        if not opt:
            return None
        call_start = text.find("(", opt.start())
        call_end = _balanced_span(text, call_start)
        if call_end is None:
            return None
        call = text[call_start:call_end]
        kw = re.search(r"\bmy_default\s*=\s*", call)
        if not kw:
            return None
        expr = call[kw.end():_expr_end(call, kw.end())].strip()
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", expr):
            value = _resolve_constant(text, expr)
        else:
            try:
                value = ast.literal_eval(expr)
            except (ValueError, SyntaxError):
                return None
        return _modules_from_value(value)
    return None


def _py_tuple(text: str, name: str) -> str | None:
    m = re.search(r"^%s\s*=\s*\(\s*(\d+)\s*,\s*(\d+)" % name, text, re.M)
    return "%s.%s" % (m.group(1), m.group(2)) if m else None


def python_support(odoo_root) -> dict | None:
    """Supported Python range declared by the checkout at `odoo_root`."""
    if not odoo_root:
        return None
    root = str(odoo_root)
    for pkg in _CORE_PACKAGES:
        for fname in ("release.py", "__init__.py"):
            text = _read_text(os.path.join(root, pkg, fname))
            if text is None:
                continue
            lo = _py_tuple(text, "MIN_PY_VERSION")
            if lo:
                return {"min": lo, "max": _py_tuple(text, "MAX_PY_VERSION"), "source": fname}

    setup = _read_text(os.path.join(root, "setup.py"))
    if setup:
        m = re.search(r"""python_requires\s*=\s*(['"])([^'"]*)\1""", setup)
        if m:
            spec = m.group(2)
            lo = re.search(r">=\s*(\d+\.\d+)", spec)
            hi = re.search(r"<=\s*(\d+\.\d+)", spec)
            if lo:
                return {"min": lo.group(1), "max": hi.group(1) if hi else None,
                        "source": "setup.py"}

    control = _read_text(os.path.join(root, "debian", "control"))
    if control:
        m = re.search(r"^X-Python-Version:\s*[<>=~ ]*(\d+\.\d+)", control, re.M)
        if m:
            ver = m.group(1)
            if ver.startswith("2."):
                return {"min": ver, "max": ver, "source": "debian"}
            return {"min": ver, "max": None, "source": "debian"}

    for launcher in ("odoo-bin", "openerp-server"):
        text = _read_text(os.path.join(root, launcher))
        if not text:
            continue
        first = text.splitlines()[0] if text.splitlines() else ""
        if re.match(r"#!.*\bpython(2(\.7)?)?\s*$", first):
            return {"min": "2.7", "max": "2.7", "source": "shebang"}
    return None


def _has_core_package(root: str) -> bool:
    return any(os.path.isfile(os.path.join(root, pkg, "release.py")) for pkg in _CORE_PACKAGES)


# The server launcher at a checkout root: `openerp-server` on the series whose core package is
# `openerp/`, `odoo-bin` afterwards. Newest spelling first.
_LAUNCHERS = ("odoo-bin", "openerp-server")


def core_launcher(root) -> str | None:
    """The executable Odoo server launcher at checkout root `root`, or None."""
    if not root:
        return None
    for name in _LAUNCHERS:
        path = os.path.join(str(root), name)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def _root_candidates(odoo_root, addons_paths):
    """Where a checkout root may be: the declared root first, then each addons_path entry, its
    parent and its grandparent (a core `addons` dir sits in the checkout root, `odoo/addons` or
    `openerp/addons` one level deeper)."""
    out = []
    if odoo_root:
        out.append(str(odoo_root).rstrip("/") or "/")
    for entry in addons_paths or []:
        entry = str(entry).rstrip("/")
        if not entry:
            continue
        parent = os.path.dirname(entry)
        for cand in (entry, parent, os.path.dirname(parent)):
            if cand and cand not in out:
                out.append(cand)
    return out


def locate_odoo_root(odoo_root=None, addons_paths=None) -> str | None:
    """The Odoo checkout root, from a declared root or an addons_path: the first candidate that
    holds Odoo's core package or its server launcher."""
    for cand in _root_candidates(odoo_root, addons_paths):
        if _has_core_package(cand) or core_launcher(cand):
            return cand
    return None


def locate_odoo_launcher(odoo_root=None, addons_paths=None) -> str | None:
    """The executable server launcher (`odoo-bin`, or `openerp-server` on the oldest series) of
    the first candidate root that has one - the same candidates locate_odoo_root walks."""
    for cand in _root_candidates(odoo_root, addons_paths):
        found = core_launcher(cand)
        if found:
            return found
    return None


# ---------------------------------------------------------------- command-line option facts
#
# Series boundaries a build depends on are declared by the checkout's own `tools/config.py`: the
# options it adds (`group.add_option("-p", "--http-port", dest="http_port", ...)`), their dests and
# whether they take a value. Reading them here is what lets a new series need no plugin edit.

# optparse actions that consume no value; a `callback` consumes one only when it declares a
# `type` (and not `nargs=0`).
_NO_VALUE_ACTIONS = frozenset(("store_true", "store_false", "store_const", "append_const", "count",
                               "help", "version"))
_FLAG_RE = re.compile(r"""\s*(['"])(-{1,2}[A-Za-z0-9][A-Za-z0-9_-]*)\1\s*,?""")
_KW_RE = r"""\b%s\s*=\s*(['"])([^'"]*)\1"""


def _core_config_text(odoo_root):
    """(core package, text of its tools/config.py) for the checkout at `odoo_root`, newest package
    spelling first; (None, None) when neither is readable."""
    if not odoo_root:
        return None, None
    for pkg in _CORE_PACKAGES:
        text = _read_text(os.path.join(str(odoo_root), pkg, "tools", "config.py"))
        if text is not None:
            return pkg, text
    return None, None


def cli_options(odoo_root) -> dict | None:
    """Every option the checkout's config.py adds: {"--long-name": {"short": "p" | None,
    "dest": "http_port" | None, "takes_value": bool}}. Long names are kept as declared (the oldest
    series spell some with `_`, e.g. `--db_user`). None when config.py is unreadable."""
    _pkg, text = _core_config_text(odoo_root)
    if text is None:
        return None
    text = _strip_comment_lines(text)
    out = {}
    for m in re.finditer(r"\badd_option\(", text):
        end = _balanced_span(text, m.end() - 1)
        if end is None:
            continue
        call = text[m.end():end - 1]
        flags = []
        pos = 0
        while True:
            fm = _FLAG_RE.match(call, pos)
            if not fm:
                break
            flags.append(fm.group(2))
            pos = fm.end()
        longs = [f for f in flags if f.startswith("--")]
        if not longs:
            continue
        short = next((f[1:] for f in flags if not f.startswith("--") and len(f) == 2), None)
        dest = re.search(_KW_RE % "dest", call)
        action = re.search(_KW_RE % "action", call)
        action = action.group(2) if action else "store"
        if action == "callback":
            takes_value = (re.search(r"\btype\s*=", call) is not None
                           and re.search(r"\bnargs\s*=\s*0\b", call) is None)
        else:
            takes_value = action not in _NO_VALUE_ACTIONS
        for name in longs:
            out[name] = {"short": short, "dest": dest.group(2) if dest else None,
                         "takes_value": takes_value}
    return out


def _declared(options, *names):
    """The first of `names` the option map declares (its entry), else None."""
    for name in names:
        if name in options:
            return options[name]
    return None


def demo_opt_in(odoo_root) -> bool | None:
    """True when the checkout declares `--with-demo` (demo data is OFF by default and opt-in),
    False when it declares only `--without-demo` (demo loads by default), None when config.py is
    unreadable or declares neither - never a guess."""
    options = cli_options(odoo_root)
    if options is None:
        return None
    if "--with-demo" in options:
        return True
    if "--without-demo" in options:
        return False
    return None


def without_demo_declared(odoo_root) -> bool | None:
    """True when the checkout declares `--without-demo` (a build can state "no demo" explicitly,
    so no config-file value flips it), False when config.py is readable and does not, None when it
    is unreadable - never a guess."""
    options = cli_options(odoo_root)
    if options is None:
        return None
    return "--without-demo" in options


def http_port_key(odoo_root) -> str | None:
    """The dest (= odoo.conf key; `--` + key with `_` as `-` is the flag) of the main HTTP port
    option: `--http-port` where declared (a hidden `--xmlrpc-port` alias may sit beside it), else
    `--xmlrpc-port`. None when neither is declared or config.py is unreadable."""
    entry = _declared(cli_options(odoo_root) or {}, "--http-port", "--xmlrpc-port")
    return entry["dest"] if entry else None


def second_port_key(odoo_root) -> str | None:
    """The dest (= odoo.conf key) of the second listening port option: `--gevent-port` where
    declared (a deprecated `--longpolling-port` alias may sit beside it), else
    `--longpolling-port`. None when neither is declared or config.py is unreadable."""
    entry = _declared(cli_options(odoo_root) or {}, "--gevent-port", "--longpolling-port")
    return entry["dest"] if entry else None


def dev_takes_value(odoo_root) -> bool | None:
    """True when the checkout's `--dev` option takes a value (so `--dev=all` is valid), False
    when `--dev` is a boolean flag or absent, None when config.py is unreadable."""
    options = cli_options(odoo_root)
    if options is None:
        return None
    entry = options.get("--dev")
    return bool(entry and entry["takes_value"])


def short_options(odoo_root) -> dict | None:
    """{char: {"long": name, "takes_value": bool}} for every short option the checkout declares,
    plus optparse's own -h/--help. The long name is spelled with `-` for `_` (`-r` -> `db-user`),
    the form odoo-bin accepts for both spellings. None when config.py is unreadable."""
    options = cli_options(odoo_root)
    if options is None:
        return None
    out = {"h": {"long": "help", "takes_value": False}}
    for name, entry in options.items():
        if entry["short"]:
            out[entry["short"]] = {"long": name[2:].replace("_", "-"),
                                   "takes_value": entry["takes_value"]}
    return out


def core_package(odoo_root) -> str | None:
    """The checkout's core package directory name - `odoo`, or `openerp` on the oldest series -
    which is also the root of its logger namespace. None when neither holds a release.py."""
    if not odoo_root:
        return None
    for pkg in _CORE_PACKAGES:
        if os.path.isfile(os.path.join(str(odoo_root), pkg, "release.py")):
            return pkg
    return None


_SERVER_EXPORT_OPTIONS = ("--i18n-export", "--modules", "--language")
_I18N_COMMAND = "i18n"
_I18N_SUBCOMMAND = "export"
_ADD_ARGUMENT_RE = re.compile(r"([A-Za-z_][\w.]*)\.add_argument\(")


def _argument_flags(text):
    """[(receiver, [flags])] for every `<receiver>.add_argument(...)` call in `text` (an argparse
    parser module): the leading quoted option strings of each call, e.g.
    ("self.export_parser", ["-o", "--output"])."""
    out = []
    for m in _ADD_ARGUMENT_RE.finditer(text):
        end = _balanced_span(text, m.end() - 1)
        if end is None:
            continue
        call, flags, pos = text[m.end():end - 1], [], 0
        while True:
            fm = _FLAG_RE.match(call, pos)
            if not fm:
                break
            flags.append(fm.group(2))
            pos = fm.end()
        out.append((m.group(1), flags))
    return out


def i18n_export_cli(odoo_root) -> dict | None:
    """The command line that exports one module's translation file on this checkout (see the
    module docstring): the server command where config.py declares --i18n-export, --modules and
    --language (each taking a value), else the `i18n` subcommand whose `export` subparser declares
    --output and --languages and whose parsers declare --config and --database. None when neither
    is fully declared."""
    options = cli_options(odoo_root)
    if options is None:
        return None
    server = [options.get(name) for name in _SERVER_EXPORT_OPTIONS]
    if all(entry and entry["takes_value"] for entry in server):
        return {"form": "server", "export": "--i18n-export", "modules": "--modules",
                "language": "--language"}
    pkg = core_package(odoo_root)
    text = _read_text(os.path.join(str(odoo_root), pkg, "cli", _I18N_COMMAND + ".py")) if pkg else None
    if text is None:
        return None
    text = _strip_comment_lines(text)
    if not re.search(r"add_parser\(\s*(['\"])%s\1" % _I18N_SUBCOMMAND, text):
        return None
    every, export = set(), set()
    for receiver, flags in _argument_flags(text):
        longs = {f for f in flags if f.startswith("--")}
        every |= longs
        if receiver.split(".")[-1] == _I18N_SUBCOMMAND + "_parser":
            export |= longs
    if not ({"--output", "--languages"} <= export and {"--config", "--database"} <= every):
        return None
    return {"form": "subcommand", "command": _I18N_COMMAND, "subcommand": _I18N_SUBCOMMAND,
            "config": "--config", "database": "--database", "output": "--output",
            "languages": "--languages"}


_I18N_KEYS = {"form": "I18N_FORM", "export": "I18N_EXPORT_FLAG", "modules": "I18N_MODULES_FLAG",
              "language": "I18N_LANGUAGE_FLAG", "command": "I18N_COMMAND",
              "subcommand": "I18N_SUBCOMMAND", "config": "I18N_CONFIG_FLAG",
              "database": "I18N_DATABASE_FLAG", "output": "I18N_OUTPUT_FLAG",
              "languages": "I18N_LANGUAGES_FLAG"}


_MATRIX_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "odoo-python-matrix.json")


def _version_key(ver: str):
    return tuple(int(p) for p in re.findall(r"\d+", ver or ""))


def _within(ver, lo, hi) -> bool:
    k = _version_key(ver)
    if not k:
        return False
    if lo and k < _version_key(lo):
        return False
    if hi and k > _version_key(hi):
        return False
    return True


def python_recommendation(series, odoo_root=None, matrix_path=None) -> dict | None:
    """Python to build a venv with for `series`: source range first, table fallback."""
    entry = {}
    try:
        with open(matrix_path or _MATRIX_DEFAULT, encoding="utf-8") as fh:
            entry = (json.load(fh).get("odoo_python_matrix") or {}).get(str(series)) or {}
    except (OSError, ValueError, AttributeError):
        entry = {}
    facts = python_support(odoo_root) if odoo_root else None
    if facts:
        lo, hi, source = facts["min"], facts["max"], facts["source"]
        pick = entry.get("recommended")
        recommended = pick if pick and _within(pick, lo, hi) else lo
    elif entry.get("min"):
        lo, hi, source = entry["min"], entry.get("max"), "matrix"
        recommended = entry.get("recommended") or lo
    else:
        return None
    return {"recommended": recommended, "min": lo, "max": hi, "source": source,
            "python2": _version_key(lo)[:1] == (2,)}


def _self_check_regex(module: str):
    # The module's own name as a string literal, used as the left operand of
    # `in` / `not in`, with `server_wide_modules` inside the same expression
    # (bounded window; line breaks allowed for wrapped calls).
    name = re.escape(module)
    return re.compile(
        r"""(['"])%s\1\s*(?:not\s+)?in\b[^:;\n]*(?:\n[^:;\n]*){0,3}?\b%s\b"""
        % (name, _OPTION_KEY)
    )


def _strip_comment_lines(text: str) -> str:
    return "\n".join("" if ln.lstrip().startswith("#") else ln for ln in text.splitlines())


def _module_self_checks(module_dir: str, module: str) -> bool:
    pattern = _self_check_regex(module)
    for dirpath, dirnames, filenames in os.walk(module_dir):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fname in filenames:
            if not fname.endswith(".py") or fname in _DESCRIPTORS:
                continue
            path = os.path.join(dirpath, fname)
            try:
                if os.path.getsize(path) > _MAX_SCAN_BYTES:
                    continue
            except OSError:
                continue
            text = _read_text(path)
            if not text or _OPTION_KEY not in text:
                continue
            if pattern.search(_strip_comment_lines(text)):
                return True
    return False


def self_declared_server_wide(addons_paths) -> list[str]:
    """Modules under `addons_paths` whose code checks their own name against
    the `server_wide_modules` option."""
    found = set()
    for base in addons_paths or []:
        if not base or not os.path.isdir(str(base)):
            continue
        try:
            entries = sorted(os.listdir(str(base)))
        except OSError:
            continue
        for entry in entries:
            mdir = os.path.join(str(base), entry)
            if not os.path.isdir(mdir):
                continue
            if not any(os.path.isfile(os.path.join(mdir, d)) for d in _DESCRIPTORS):
                continue
            if _module_self_checks(mdir, entry):
                found.add(entry)
    return sorted(found)


_WARNING_RE = re.compile(
    r"""[Tt]he module [`'"]?([A-Za-z0-9_]+)[`'"]? should be loaded in server[- ]wide mode"""
)


def server_wide_warning_modules(log_text) -> list[str]:
    """Module names Odoo's log says must be loaded server-wide."""
    if not log_text:
        return []
    return sorted(set(_WARNING_RE.findall(log_text)))


# ---------------------------------------------------------------- CLI

def _emit(key: str, value: str) -> None:
    sys.stdout.write("%s=%s\n" % (key, value))


def _usage() -> int:
    sys.stderr.write(
        "usage: odoo_source_facts.py core-load <odoo_root> | cli-facts <odoo_root> | "
        "python <odoo_root> | "
        "i18n-facts <odoo_root> | python-suggest <series> [<odoo_root>] | locate-root|locate-launcher [--odoo-root <dir>] "
        "[<addons_dir>...] | "
        "self-declared <addons_dir>... | warnings [<logfile>...]\n"
    )
    return 2


def main(argv) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        return _usage()
    cmd, args = argv[0], argv[1:]
    if cmd == "core-load":
        if len(args) != 1:
            return _usage()
        mods = core_server_wide_modules(args[0])
        if mods is None:
            sys.stderr.write("core --load default unreadable under %s\n" % args[0])
            return 3
        _emit("CORE_SERVER_WIDE_MODULES", ",".join(mods))
        return 0
    if cmd == "cli-facts":
        if len(args) != 1:
            return _usage()
        if cli_options(args[0]) is None:
            sys.stderr.write("no readable odoo/tools/config.py (openerp/tools/config.py on the "
                             "oldest series) under %s\n" % args[0])
            return 3
        demo, dev = demo_opt_in(args[0]), dev_takes_value(args[0])
        _emit("CORE_PACKAGE", core_package(args[0]) or "")
        _emit("DEMO_OPT_IN", "" if demo is None else ("1" if demo else "0"))
        _emit("WITHOUT_DEMO", "1" if without_demo_declared(args[0]) else "0")
        _emit("HTTP_PORT_KEY", http_port_key(args[0]) or "")
        _emit("SECOND_PORT_KEY", second_port_key(args[0]) or "")
        _emit("DEV_TAKES_VALUE", "1" if dev else "0")
        return 0
    if cmd == "i18n-facts":
        if len(args) != 1:
            return _usage()
        cli = i18n_export_cli(args[0])
        if cli is None:
            sys.stderr.write("no i18n export command line declared under %s (neither --i18n-export "
                             "in tools/config.py nor an export subparser in cli/i18n.py)\n" % args[0])
            return 3
        for key, value in cli.items():
            _emit(_I18N_KEYS[key], value)
        return 0
    if cmd == "python":
        if len(args) != 1:
            return _usage()
        info = python_support(args[0])
        if info is None:
            sys.stderr.write("python support unreadable under %s\n" % args[0])
            return 3
        _emit("PY_MIN", info["min"])
        _emit("PY_MAX", info["max"] or "")
        _emit("PY_SOURCE", info["source"])
        return 0
    if cmd == "python-suggest":
        if len(args) not in (1, 2):
            return _usage()
        info = python_recommendation(args[0], args[1] if len(args) == 2 else None)
        if info is None:
            sys.stderr.write("no Python facts for Odoo %s (no readable checkout, no table entry)\n"
                             % args[0])
            return 3
        _emit("PY_RECOMMENDED", info["recommended"])
        _emit("PY_MIN", info["min"])
        _emit("PY_MAX", info["max"] or "")
        _emit("PY_SOURCE", info["source"])
        _emit("PY_PYTHON2", "1" if info["python2"] else "0")
        return 0
    if cmd in ("locate-root", "locate-launcher"):
        root, paths = None, []
        it = iter(args)
        for a in it:
            if a == "--odoo-root":
                root = next(it, None)
                if root is None:
                    return _usage()
            else:
                paths.append(a)
        if cmd == "locate-root":
            found = locate_odoo_root(root, paths)
            if found is None:
                sys.stderr.write("no Odoo checkout among the given paths\n")
                return 3
            _emit("ODOO_ROOT", found)
            return 0
        launcher = locate_odoo_launcher(root, paths)
        if launcher is None:
            sys.stderr.write("no Odoo server launcher (odoo-bin / openerp-server) among the given "
                             "paths\n")
            return 3
        _emit("ODOO_LAUNCHER", launcher)
        _emit("ODOO_ROOT", os.path.dirname(launcher))
        return 0
    if cmd == "self-declared":
        if not args:
            return _usage()
        _emit("SELF_DECLARED_SERVER_WIDE", ",".join(self_declared_server_wide(args)))
        return 0
    if cmd == "warnings":
        chunks = []
        if args:
            for path in args:
                text = _read_text(path)
                if text is None:
                    sys.stderr.write("cannot read %s\n" % path)
                    return 2
                chunks.append(text)
        else:
            chunks.append(sys.stdin.read())
        _emit("SERVER_WIDE_WARNINGS", ",".join(server_wide_warning_modules("\n".join(chunks))))
        return 0
    sys.stderr.write("unknown subcommand %r\n" % cmd)
    return _usage()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
