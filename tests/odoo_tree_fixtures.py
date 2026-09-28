"""Fixture Odoo checkouts for the build-facts tests (not a test module itself).

A fixture tree carries only what the build-fact readers look at: the core package's
`release.py` and its `tools/config.py` with the `--load` option spelled the way that series spells
it (a string `my_default` up to 18.0, the `DEFAULT_SERVER_WIDE_MODULES` constant from 19.0) and
the options whose shape changes across series (demo, the two listening ports, `--dev`, `-t`, the
i18n export options), under `openerp/` before 10.0 and `odoo/` after - plus, where the series
exports translations through the `i18n` subcommand instead of the server's `--i18n-export`
(I18N_SUBCOMMAND), that command's `cli/i18n.py` parser declarations. CORE_LOAD and OPTIONS are what each series' own
config.py declares - read from the real checkouts (`real_checkout` below finds them when present,
and test_odoo_source_facts holds every fixture to the real tree it stands for).
"""

from __future__ import annotations

import os
from pathlib import Path

SERIES = ("8.0", "9.0", "10.0", "11.0", "12.0", "13.0", "14.0", "15.0", "16.0", "17.0", "18.0",
          "19.0", "20.0")

CORE_LOAD = {
    "8.0": ["web", "web_kanban"], "9.0": ["web", "web_kanban"], "10.0": ["web", "web_kanban"],
    "11.0": ["web"],
    "12.0": ["base", "web"], "13.0": ["base", "web"], "14.0": ["base", "web"],
    "15.0": ["base", "web"], "16.0": ["base", "web"], "17.0": ["base", "web"],
    "18.0": ["base", "web"],
    "19.0": ["base", "rpc", "web"], "20.0": ["base", "rpc", "web"],
}

# Per series: (declares --with-demo, main port options, second port options, --dev shape, -t long).
# A port entry is (long flag, dest); --dev is "value", "flag" (store_true) or None (absent).
_MAIN_OLD = (("--xmlrpc-port", "xmlrpc_port"),)
_MAIN_NEW = (("--http-port", "http_port"), ("--xmlrpc-port", "http_port"))
_LONGPOLL = (("--longpolling-port", "longpolling_port"),)
_BOTH = (("--longpolling-port", "longpolling_port"), ("--gevent-port", "gevent_port"))
_GEVENT = (("--gevent-port", "gevent_port"),)
OPTIONS = {
    "8.0": (False, _MAIN_OLD, _LONGPOLL, None, "timezone"),
    "9.0": (False, _MAIN_OLD, _LONGPOLL, "flag", None),
    "10.0": (False, _MAIN_OLD, _LONGPOLL, "value", None),
    "11.0": (False, _MAIN_NEW, _LONGPOLL, "value", None),
    "12.0": (False, _MAIN_NEW, _LONGPOLL, "value", None),
    "13.0": (False, _MAIN_NEW, _LONGPOLL, "value", None),
    "14.0": (False, _MAIN_NEW, _LONGPOLL, "value", None),
    "15.0": (False, _MAIN_NEW, _LONGPOLL, "value", None),
    "16.0": (False, _MAIN_NEW, _BOTH, "value", None),
    "17.0": (False, _MAIN_NEW, _BOTH, "value", "test-tags"),
    "18.0": (False, _MAIN_NEW, _GEVENT, "value", "test-tags"),
    "19.0": (True, _MAIN_NEW, _GEVENT, "value", "test-tags"),
    "20.0": (True, _MAIN_NEW, _GEVENT, "value", "test-tags"),
}

# Short options every series declares with one meaning (long name as declared, value-taking unless
# a store_true flag), and the series that no longer declare one.
_SHORTS = (("c", "--config", True), ("s", "--save", False), ("i", "--init", True),
           ("u", "--update", True), ("P", "--import-partial", True), ("D", "--data-dir", True),
           ("d", "--database", True), ("r", "--db_user", True), ("w", "--db_password", True),
           ("l", "--language", True))
_SHORTS_ABSENT = {"19.0": ("l",), "20.0": ("l", "s")}
# Long options a series no longer declares at all (its short went with it): -l/--language left
# config.py with the rest of the server's i18n export options when the `i18n` subcommand took them.
_LONGS_ABSENT = {"19.0": ("--language",), "20.0": ("--language",)}
# The series whose translations export through the `i18n` subcommand (no --i18n-export option).
I18N_SUBCOMMAND = ("19.0", "20.0")
_SERVER_I18N_OPTIONS = ('        group.add_option("--i18n-export", dest="translate_out")',
                        '        group.add_option("--modules", dest="translate_modules")')
# The parser declarations of the real `odoo/cli/i18n.py` export subcommand (19.0 and 20.0 alike).
_I18N_CLI = """\
class I18n(Command):
    def __init__(self, *args, **kwargs):
        subparsers = self.parser.add_subparsers(dest='subcommand', required=True)
        self.import_parser = subparsers.add_parser('import')
        self.export_parser = subparsers.add_parser(
            'export',
            help="Export i18n files")
        self.loadlang_parser = subparsers.add_parser('loadlang')
        for parser in (self.import_parser, self.export_parser, self.loadlang_parser):
            parser.add_argument(
                '-c', '--config', dest='config')
            parser.add_argument(
                '-d', '--database', dest='db_name', default=None)
        self.import_parser.add_argument('files', nargs='+', metavar='FILE')
        self.import_parser.add_argument('-l', '--language', dest='language', required=True)
        self.export_parser.add_argument(
            '-l', '--languages', dest='languages', nargs='+', default=['pot'], metavar='LANG')
        self.export_parser.add_argument(
            'modules', nargs='+', metavar='MODULE')
        self.export_parser.add_argument(
            '-o', '--output', metavar="FILE", dest='output')
        self.loadlang_parser.add_argument('-l', '--languages', dest='languages', nargs='+')
"""

CHECKOUTS = Path(os.environ.get("ODOO_SOURCE_CHECKOUTS") or (Path.home() / "git"))


def _major(series):
    return int(series.split(".", 1)[0])


def core_package(series):
    return "openerp" if _major(series) < 10 else "odoo"


def _option_lines(series):
    with_demo, main, second, dev, t_long = OPTIONS[series]
    out = ['        group.add_option("--without-demo", dest="without_demo", my_default=False)']
    if with_demo:
        out.append('        group.add_option("--with-demo", dest="with_demo", action=\'store_true\')')
    for flag, dest in main:
        short = '"-p", ' if flag == "--http-port" else ""
        out.append('        group.add_option(%s"%s", dest="%s", type="int")' % (short, flag, dest))
    for flag, dest in second:
        out.append('        group.add_option("%s", dest="%s", type="int")' % (flag, dest))
    if dev == "value":
        out.append("        group.add_option('--dev', dest='dev_mode', type=\"string\")")
    elif dev == "flag":
        out.append("        group.add_option('--dev', dest='dev_mode', action='store_true')")
    if t_long:
        out.append('        group.add_option("-t", "--%s", dest="%s")' % (t_long, t_long.replace("-", "_")))
    if series not in I18N_SUBCOMMAND:
        out.extend(_SERVER_I18N_OPTIONS)
    for char, flag, takes_value in _SHORTS:
        if flag in _LONGS_ABSENT.get(series, ()):
            continue
        if char in _SHORTS_ABSENT.get(series, ()):
            out.append('        group.add_option("%s", dest="%s", type="string")' % (flag, flag[2:]))
            continue
        action = "" if takes_value else ", action='store_true'"
        out.append('        group.add_option("-%s", "%s", dest="%s"%s)' % (char, flag, flag[2:], action))
    return "\n".join(out) + "\n"


def write_checkout(root: Path, series: str, with_addons: bool = True) -> Path:
    """A minimal checkout of `series` at `root` (its config.py declares CORE_LOAD[series] and
    OPTIONS[series]); returns root. An `addons/` dir is created beside the core package, as in a
    real checkout (with_addons=False leaves it to the caller). Rewriting a root for another series
    removes the other core package, so the tree never holds two."""
    import shutil
    for other in ("odoo", "openerp"):
        if other != core_package(series) and (root / other).is_dir():
            shutil.rmtree(root / other)
    pkg = root / core_package(series)
    tools = pkg / "tools"
    tools.mkdir(parents=True, exist_ok=True)
    (pkg / "release.py").write_text("version_info = (%d, 0, 0, 'final', 0, '')\n" % _major(series),
                                    encoding="utf-8")
    mods = CORE_LOAD[series]
    if _major(series) >= 19:
        text = ("DEFAULT_SERVER_WIDE_MODULES = %r\n\n"
                "class configmanager:\n"
                "    def __init__(self):\n"
                "        group.add_option(\"--load\", dest=\"server_wide_modules\", type='comma',\n"
                "                         metavar='MODULE,...', my_default=DEFAULT_SERVER_WIDE_MODULES,\n"
                "                         help=\"Comma-separated list of server-wide modules.\")\n"
                % (mods,)) + _option_lines(series)
    else:
        text = ("class configmanager(object):\n"
                "    def __init__(self):\n"
                "        group.add_option(\"--load\", dest=\"server_wide_modules\", "
                "help=\"Comma-separated list of server-wide modules.\", my_default='%s')\n"
                % ",".join(mods)) + _option_lines(series)
    (tools / "config.py").write_text(text, encoding="utf-8")
    if series in I18N_SUBCOMMAND:
        (pkg / "cli").mkdir(exist_ok=True)
        (pkg / "cli" / "i18n.py").write_text(_I18N_CLI, encoding="utf-8")
    elif (pkg / "cli" / "i18n.py").exists():
        (pkg / "cli" / "i18n.py").unlink()
    if with_addons:
        (root / "addons").mkdir(exist_ok=True)
    return root


def real_checkout(series):
    """The real checkout of `series` when this machine has one, else None."""
    root = CHECKOUTS / ("odoo_%s" % series)
    return root if (root / core_package(series) / "tools" / "config.py").is_file() else None
