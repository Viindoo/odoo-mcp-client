"""tools_i18n.py - instance_i18n_export: translation files exported from a lease's database.

  instance_i18n_export  starts `55-instance-ops.sh i18n-export` DETACHED through jobs.start (the
                        same job machinery as instance_build; job_wait reports it - its reading
                        of an export job, `exports` included, lives beside job_wait in
                        tools_instance), with every connection fact read from the lease
                        row. Per module the `.pot` template
                        is exported FIRST, then one `.po` per requested language, all from the
                        lease's one database, by Odoo's own exporter with the command line the
                        lease's checkout declares (the server's --i18n-export, or the `i18n
                        export` subcommand - odoo_source_facts.i18n_export_cli; the script spells
                        it). The files are never edited afterwards (cmd_i18n_export).

Gates, checked here before anything starts - FIRST whether another job runs on the database
(DATABASE_BUSY, tools_instance.refuse_if_busy: while a build runs, the database is a moment of that
build, and the gates below would read it) - then on the DATABASE's facts (tools_lease.database_facts:
read from the database itself - ir_module_module.demo, res_lang.active - and, only when it cannot
be read, from the builds every lease on it recorded; so a lease taken on a forwarded database is
judged by what that database holds):
  - demo must have been loaded for every EXPORTED module (I18N_EXPORT_NEEDS_DEMO): every record a
    module owns is exported, demo records included, so a module installed without its demo data
    yields a truncated catalog - and that is a fact of each module (its own
    ir_module_module.demo), never of the database as a whole, where another module's demo says
    nothing about this one. Only when the database cannot be read does the lease-recorded demo
    answer, and the export job then asks the database per module itself (i18n-state);
  - en_US and every requested language must be loaded (active in the database, or - unreadable -
    proven loaded by a finished build) (I18N_LANGUAGE_NOT_LOADED): an export in a language that is
    not loaded has every msgstr empty;
  - the checkout must declare an export command line (ODOO_SOURCE_FACT_UNKNOWN);
  - each module must resolve in exactly ONE directory of the lease's addons path + core addons
    (MODULE_SHADOWED): Odoo's code-term walk reads every copy it finds, so a shadowed module's
    export would carry the other copy's references and terms too.
The script then asks the database (odoo_db.py i18n-state) whether each module is installed with its
demo data and each language active, and reads each language's ISO code for the file name.

Destinations: each module's own `i18n/` directory (the module found on the lease's addons path,
or the checkout's core addons), where Odoo reads translations from - or, with output_dir,
`<output_dir>/<module>/`. File names: `<module>.pot`, and per language the name the module already
uses (its own i18n/ directory decides, output_dir or not - 55-instance-ops.sh cmd_i18n_export):
`<code>.po` when it ships that and no `<iso_code>.po`, else `<iso_code>.po` (Odoo's own export
name); both present is refused by the job (I18N_PO_FILE_AMBIGUOUS).
"""

import datetime
import os
import uuid

from . import cli, jobs, tools_instance, tools_lease
from .errors import ToolError
from .tools_lease import HANDLE_SCHEMA, _obj

I18N_OP = "i18n-export"
_MANIFESTS = ("__manifest__.py", "__openerp__.py")


def _languages(args):
    """The requested target languages, validated, deduplicated, in order."""
    out = []
    for lang in args.get("languages") or []:
        if not tools_instance._LANG_RE.match(lang):
            raise ToolError("INVALID_ARGUMENTS",
                            "arguments.languages: %r is not a language code (e.g. vi_VN, fr_BE, "
                            "sr@latin)" % lang)
        if lang == tools_instance.BASE_LANGUAGE:
            raise ToolError("INVALID_ARGUMENTS",
                            "arguments.languages: %s is Odoo's source language - its terms are the "
                            ".pot template, which is always exported; Odoo ships no %s.po. Pass only "
                            "the target languages" % (lang, lang))
        if lang not in out:
            out.append(lang)
    return out


def _modules(args):
    out = []
    for m in args["modules"]:
        if not tools_instance._MODULE_RE.match(m):
            raise ToolError("INVALID_ARGUMENTS", "arguments.modules: %r is not a module name" % m)
        if m not in out:
            out.append(m)
    return out


def _addons_dirs(row, lease):
    """Where Odoo finds modules for this lease: its addons_path, then the checkout's core addons
    (`<core package>/addons`, which Odoo always adds itself)."""
    dirs = list(lease.get("addons_path") or [])
    root = tools_instance.lease_checkout(row, lease)
    if root:
        pkg = cli.load_lib("odoo_source_facts").core_package(root)
        if pkg:
            dirs.append(os.path.join(root, pkg, "addons"))
    return dirs


def _module_dirs(module, dirs):
    """Every directory `module` resolves to across `dirs`, in addons-path order; one directory
    reached through two entries (a repeated entry, a symlink) counts once."""
    found, seen = [], set()
    for base in dirs:
        path = os.path.join(base, module)
        if not any(os.path.isfile(os.path.join(path, m)) for m in _MANIFESTS):
            continue
        real = os.path.realpath(path)
        if real not in seen:
            seen.add(real)
            found.append(path)
    return found


def _destinations(modules, output_dir, row, lease, token):
    """[(module, directory its files go to, the module's own i18n/ directory)], refusing a module
    the lease cannot see (INVALID_ARGUMENTS) or one it sees twice (MODULE_SHADOWED)."""
    dirs = _addons_dirs(row, lease)
    out = []
    for m in modules:
        paths = _module_dirs(m, dirs)
        if not paths:
            raise ToolError("INVALID_ARGUMENTS",
                            "arguments.modules: %s is not a module on the lease's addons path (%s)" % (
                                m, ", ".join(dirs) or "none"))
        if len(paths) > 1:
            raise ToolError("MODULE_SHADOWED",
                            "lease %s: module %s resolves in %d addons directories (%s); Odoo's "
                            "export reads the source of every copy, so its catalog would mix them" % (
                                token[:8], m, len(paths), ", ".join(paths)),
                            {"token_prefix": token[:8], "module": m, "paths": paths})
        own = os.path.join(paths[0], "i18n")
        out.append((m, os.path.join(output_dir, m) if output_dir else own, own))
    return out


_SOURCE_WORDS = {tools_lease.FACTS_FROM_DATABASE: "read from the database itself",
                 tools_lease.FACTS_FROM_LEASES: "the database could not be read; per the builds its "
                                                "leases recorded"}


def _modules_without_demo(facts, modules):
    """The exported modules the database itself says are installed WITHOUT their own demo data
    (facts["modules"], read per module); [] when it was not read per module. A module the
    database does not hold installed is left to the job (I18N_MODULE_NOT_INSTALLED)."""
    known = facts.get("modules") or {}
    return [m for m in modules
            if (known.get(m) or {}).get("state") == "installed" and not known[m]["demo"]]


def _require_fit_database(facts, lease, token, languages, modules):
    """`facts` = tools_lease.database_facts: the database itself (per exported module too), else
    its leases' build records."""
    where = "lease %s, database %s (%s)" % (token[:8], lease.get("db_name") or "?",
                                            _SOURCE_WORDS[facts["source"]])
    if facts["demo"] is not True:
        raise ToolError("I18N_EXPORT_NEEDS_DEMO",
                        "%s: no demo data (demo: %s), so an export would miss every term of the "
                        "modules' demo records" % (
                            where, {None: "not known", False: "none loaded"}.get(facts["demo"])),
                        {"token_prefix": token[:8], "db_name": lease.get("db_name") or "",
                         "demo": facts["demo"], "facts_source": facts["source"],
                         "modules_without_demo": []})
    bare = _modules_without_demo(facts, modules)
    if bare:
        raise ToolError("I18N_EXPORT_NEEDS_DEMO",
                        "%s: %s installed WITHOUT %s own demo data (other modules of the database "
                        "have theirs), so an export would miss every term of %s demo records" % (
                            where, ", ".join(bare), "their" if len(bare) > 1 else "its",
                            "their" if len(bare) > 1 else "its"),
                        {"token_prefix": token[:8], "db_name": lease.get("db_name") or "",
                         "demo": facts["demo"], "facts_source": facts["source"],
                         "modules_without_demo": bare})
    wanted = [tools_instance.BASE_LANGUAGE] + languages
    missing = [lang for lang in wanted if lang not in facts["languages"]]
    if missing:
        raise ToolError("I18N_LANGUAGE_NOT_LOADED",
                        "%s: languages not loaded: %s (loaded: %s)" % (
                            where, ", ".join(missing), ", ".join(facts["languages"]) or "none"),
                        {"token_prefix": token[:8], "db_name": lease.get("db_name") or "",
                         "missing": missing, "loaded": facts["languages"],
                         "facts_source": facts["source"]})


def _export(args, ctx):
    token = args["lease_token"]
    cwd = tools_instance._cwd(args)
    modules = _modules(args)
    languages = _languages(args)
    output_dir = args.get("output_dir")
    if output_dir is not None and not os.path.isabs(output_dir):
        raise ToolError("INVALID_ARGUMENTS",
                        "arguments.output_dir: must be an absolute path, got %r" % output_dir)
    row = tools_instance._require_row(token)
    lease = tools_lease.lease_from_row(row)
    db = tools_instance._lease_field(lease, "db_name", token)
    python = tools_instance._lease_field(lease, "venv_python", token)
    addons = tools_instance._lease_field(lease, "addons_path", token)
    tools_instance.refuse_if_busy(lease)  # before any gate reads the database
    # The database itself (per exported module too), else the lease records.
    facts = tools_lease.database_facts(row, cwd=cwd, modules=modules)
    _require_fit_database(facts, lease, token, languages, modules)
    tools_instance._checkout_fact(row, lease, token,
                                  "the i18n export command line (--i18n-export in "
                                  "odoo/tools/config.py, or the export subcommand in "
                                  "odoo/cli/i18n.py)", "i18n_export_cli")
    destinations = _destinations(modules, output_dir, row, lease, token)

    argv = [I18N_OP, "--db", db, "--python", python, "--addons", tools_lease.join_addons(addons),
            "--modules", tools_instance.MODULE_LIST_SEP.join(modules)]
    if languages:
        argv += ["--languages", tools_instance.MODULE_LIST_SEP.join(languages)]
    for module, directory, own in destinations:
        argv += ["--target", "%s=%s" % (module, directory), "--i18n-dir", "%s=%s" % (module, own)]
    for flag, key in (("--db-host", "db_host"), ("--db-user", "db_user"), ("--db-port", "db_port")):
        if lease.get(key):
            argv += [flag, lease[key]]
    if lease.get("series"):
        argv += ["--version", lease["series"]]

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = os.path.join(tools_instance._logs_dir(), "%s-i18n-%s_%s" % (db, stamp, uuid.uuid4().hex[:4]))
    log_path, output_path = base + ".log", base + ".ops.log"
    meta = dict(tools_instance.job_target(lease), **{
            "kind": tools_instance.EXPORT_JOB_KIND, "op": I18N_OP, "lease_token": token,
            "log_path": log_path, "output_path": output_path, "series": lease.get("series") or "",
            "modules": modules, "export_languages": languages,
            "destinations": [{"module": m, "directory": d} for m, d, _own in destinations]})
    with tools_instance.database_job_slot(lease):
        try:
            rec = jobs.start(cli.interpreter_for(tools_instance._ops_script()) + argv, cwd,
                             env={tools_instance.OPS_LOG_ENV: log_path}, log_path_hint=output_path,
                             meta=meta)
        except (OSError, ValueError) as exc:
            raise ToolError("BUILD_START_FAILED", "cannot start the i18n export: %s" % exc,
                            {"op": I18N_OP})
    return {"job_id": rec["job_id"], "pid": rec["pid"], "op": I18N_OP, "log_path": log_path,
            "output_path": output_path, "lease_token": token, "destinations": meta["destinations"],
            "instance_handle": tools_lease.database_handle(row, lease, facts=facts,
                                                          log_path=log_path)}


# --------------------------------------------------------------------------- #
# registration
# --------------------------------------------------------------------------- #
def register(registry, ctx):
    registry.add(
        "instance_i18n_export",
        "Export translation files for modules from the database of a lease you hold or were "
        "handed, with Odoo's own exporter: per module the .pot template FIRST, then one .po per "
        "language in languages, all from that one database. Never compose an odoo-bin "
        "--i18n-export or `odoo-bin i18n export` command yourself: the tool reads which command "
        "line the lease's Odoo checkout declares (the server's --i18n-export up to the series that "
        "moved export to the `i18n export` subcommand) and passes the lease's database, venv, "
        "addons path and Postgres coordinates itself. Files land in each module's own i18n/ "
        "directory (where Odoo reads them) as <module>.pot and one .po per language named as the "
        "module already names it: <code>.po (e.g. vi_VN.po) when the module ships that and no "
        "<iso_code>.po, else <iso_code>.po (e.g. vi.po for vi_VN, Odoo's own export name) - or "
        "under output_dir/<module>/ when you pass one (same names). A module shipping both files "
        "for one language fails the job before any file is written (I18N_PO_FILE_AMBIGUOUS in "
        "output_tail: Odoo loads the full-code file last, so it wins - ask the operator which "
        "file to keep). "
        "The files are exactly what Odoo wrote: never rewrap, reorder or re-header them. A file "
        "is replaced only by a finished export, so a failed run never truncates the file it was "
        "about to replace. Refused before anything starts unless the lease's DATABASE - a "
        "forwarded one included - holds every exported module WITH its own demo data "
        "(I18N_EXPORT_NEEDS_DEMO) and has en_US plus every language in languages loaded "
        "(I18N_LANGUAGE_NOT_LOADED), and unless each module resolves in exactly one addons "
        "directory (MODULE_SHADOWED: Odoo's export would read every copy). Those facts are read from "
        "the database itself; only when it cannot be read do the builds recorded on its leases "
        "answer (diagnostics.facts_source says which). Build the export instance with instance_build "
        "op init demo on and languages = the target languages, job_wait it, then call this. Pass "
        "only target languages (en_US is the template's source, never a .po; it is refused). One "
        "build or export runs on a database at a time: while another job still runs on it "
        "(through any lease), the call is refused with DATABASE_BUSY naming that job_id - "
        "job_wait it, then call again. "
        "Returns within seconds with job_id; call job_wait(job_id) until its result is not "
        "timeout - its exports lists every file written in order (.pot first), and a module not "
        "installed (or installed without its demo data) or a language not active in the database "
        "fails the job before any file is written (I18N_MODULE_NOT_INSTALLED / "
        "I18N_EXPORT_NEEDS_DEMO / I18N_LANGUAGE_NOT_ACTIVE in output_tail). Odoo runs with a "
        "config file the tool generates, never the operator's ~/.odoorc.",
        _obj({
            "lease_token": {"type": "string", "minLength": 8,
                            "description": "Full token of the lease whose database to export from "
                                           "(lease.token or INSTANCE_HANDLE.lease_token)."},
            "modules": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1},
                        "description": "Technical names of the modules to export, each installed "
                                       "in the lease's database; each gets its own files."},
            "languages": {"type": "array", "items": {"type": "string", "minLength": 2},
                          "description": "Target language codes to export a .po for, e.g. "
                                         "[\"vi_VN\", \"fr_BE\"]; each must have been loaded by a "
                                         "finished build on this database. Omit or [] for the "
                                         ".pot template alone. Never en_US."},
            "output_dir": {"type": "string", "minLength": 1,
                           "description": "Absolute directory to write into instead of each "
                                          "module's own i18n/ directory; files go to "
                                          "<output_dir>/<module>/. Omit to write where Odoo reads "
                                          "translations from."},
            "cwd": tools_instance._CWD_PROP,
        }, ["lease_token", "modules"]),
        _obj({
            "job_id": {"type": "string"},
            "pid": {"type": "integer"},
            "op": {"type": "string"},
            "log_path": {"type": "string", "description": "The Odoo log of every export run."},
            "output_path": {"type": "string"},
            "lease_token": {"type": "string"},
            "destinations": {"type": "array",
                             "description": "Where each module's files are written.",
                             "items": _obj({"module": {"type": "string"},
                                            "directory": {"type": "string"}},
                                           ["module", "directory"])},
            "instance_handle": HANDLE_SCHEMA,
        }, ["job_id", "pid", "op", "log_path", "output_path", "lease_token", "destinations",
            "instance_handle"]),
        _export, title="Export Odoo translation files", destructive=True,
    )
