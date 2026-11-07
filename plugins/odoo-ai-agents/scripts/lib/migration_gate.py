#!/usr/bin/env python3
"""migration_gate.py - prove a pull request respects the module version and migration rule.

Stdlib only. The gate compares two addons trees on disk and never runs git or imports a
module: the manifest is parsed as a Python literal (`ast.literal_eval`), never executed.
Output is KEY=VALUE lines.

  check --base DIR --head DIR --series X.Y [--modules a,b] [--allow-short a,b]
      --base          the addons tree at the merge base of the pull request
      --head          the addons tree of the change (the worktree)
      --series        the series prefix a full migration folder name carries (e.g. 99.0)
      --modules       restrict the scope to these modules (default: every module whose
                      directory content differs between base and head)
      --allow-short   modules whose new migration folder may use the short form (no series
                      prefix)
      A module is a directory holding `__manifest__.py` or `__openerp__.py`.

  Per module in scope:
      MODULE=<name>  VERSION_BASE=<v>  VERSION_HEAD=<v>  BUMP=none|smallest|other
      MIGRATION_DIRS_NEW=<comma list or none>  MIGRATION_FILES=<comma list or none>
  then, over the whole run:
      FAIL_REASON=<module>: <reason>   (one per line)
      WARN=<module>: <reason>          (one per line)
      MIGRATION_GATE=PASS|FAIL
  Exit: 0 PASS (warnings allowed), 1 FAIL, 3 usage.

Rules (within one pull request, i.e. one change inside one series):
  1. A touched module's short manifest version is bumped at most once, by the smallest step:
     `x.y.z` -> `x.y.(z+1)`, or `x.y` -> `x.y.1`, and nothing else changed. Any other change
     (two components, +2, a downgrade, `x.y` -> `x.(y+1)`, a change of length) is BUMP=other
     and FAILs, naming the expected smallest step.
  2. A migration folder without a bump FAILs. A bump without a migration folder is a WARN
     only (a pure code change may be versioned on purpose); a bump goes with a migration
     script, or with the caller's declaration that the change moves existing data.
  3. At most one new folder under `<module>/migrations/` per module, named
     `<series>.<new short version>` (full form). The short form (no series prefix) FAILs
     unless the module is listed in --allow-short.
  4. Inside the new folder the only files are `pre-migrate.py`, `post-migrate.py`,
     `end-migrate.py` and `__init__.py`: at most one script per stage, no file named after a
     business topic, no sub-directory.
  5. A migration folder that exists at base is never modified: any added, removed or changed
     file under it FAILs.
  6. A module new in head (absent in base) carries its initial version and is out of scope
     for the bump rule; it FAILs only if it ships a `migrations/` folder, because a new
     module migrates nothing.
  7. A manifest version that carries the series prefix is compared in its short form and
     WARNs: the convention is the short form.
"""
import argparse
import ast
import hashlib
import os
import sys

MANIFESTS = ("__manifest__.py", "__openerp__.py")
STAGE_FILES = ("pre-migrate.py", "post-migrate.py", "end-migrate.py")
ALLOWED_FILES = STAGE_FILES + ("__init__.py",)
IGNORED_DIRS = ("__pycache__",)


def _manifest_path(mod_dir):
    for name in MANIFESTS:
        path = os.path.join(mod_dir, name)
        if os.path.isfile(path):
            return path
    return None


def list_modules(tree):
    """Return {name: dir} for every module directly under the addons tree."""
    found = {}
    if not os.path.isdir(tree):
        return found
    for name in sorted(os.listdir(tree)):
        path = os.path.join(tree, name)
        if os.path.isdir(path) and _manifest_path(path):
            found[name] = path
    return found


def _files(root):
    """Return {relative path: content digest} of every file under root."""
    out = {}
    for cur, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
        for n in names:
            if n.endswith(".pyc"):
                continue
            full = os.path.join(cur, n)
            with open(full, "rb") as fh:
                out[os.path.relpath(full, root)] = hashlib.sha256(fh.read()).hexdigest()
    return out


def read_version(mod_dir):
    """Return the manifest `version` string, or None when absent or not a literal."""
    with open(_manifest_path(mod_dir), encoding="utf-8") as fh:
        try:
            data = ast.literal_eval(fh.read().strip())
        except (ValueError, SyntaxError):
            return None
    version = data.get("version") if isinstance(data, dict) else None
    return version if isinstance(version, str) else None


def short_form(version, series):
    """Return (short version, whether the series prefix was carried)."""
    prefix = series + "."
    if version.startswith(prefix):
        return version[len(prefix):], True
    return version, False


def _tuple(version):
    try:
        return tuple(int(p) for p in version.split("."))
    except ValueError:
        return None


def smallest_step(base_short):
    """Return the smallest bump of a short version, or None when it is not numeric."""
    b = _tuple(base_short)
    if b is None:
        return None
    if len(b) == 2:
        return base_short + ".1"
    return ".".join(str(p) for p in b[:-1] + (b[-1] + 1,))


def classify_bump(base_short, head_short):
    if base_short == head_short:
        return "none"
    if head_short == smallest_step(base_short):
        return "smallest"
    return "other"


def _migration_dirs(mod_dir):
    root = os.path.join(mod_dir, "migrations")
    if not os.path.isdir(root):
        return []
    return sorted(d for d in os.listdir(root)
                  if os.path.isdir(os.path.join(root, d)) and d not in IGNORED_DIRS)


def _check_new_module(name, head_dir, fails, out):
    out.append("MODULE=" + name)
    out.append("VERSION_BASE=none")
    out.append("VERSION_HEAD=%s" % read_version(head_dir))
    out.append("BUMP=none")
    out.append("MIGRATION_DIRS_NEW=" + (",".join(_migration_dirs(head_dir)) or "none"))
    out.append("MIGRATION_FILES=none")
    if os.path.isdir(os.path.join(head_dir, "migrations")):
        fails.append("%s: a new module ships a migrations/ folder; a new module migrates nothing"
                     % name)


def _check_new_folders(name, head_dir, new_dirs, h_short, series, allow_short, fails):
    """Rules 3 and 4 for every new migration folder; return the listed files."""
    listed = []
    expected = "%s.%s" % (series, h_short)
    for d in new_dirs:
        folder = os.path.join(head_dir, "migrations", d)
        names = [n for n in sorted(os.listdir(folder))
                 if n not in IGNORED_DIRS and not n.endswith(".pyc")]
        listed.extend("%s/%s" % (d, n) for n in names)
        if d == h_short:
            if name not in allow_short:
                fails.append("%s: migration folder %s uses the short form; name it %s"
                             % (name, d, expected))
        elif d != expected:
            fails.append("%s: migration folder %s does not match the bumped version; expected %s"
                         % (name, d, expected))
        for n in names:
            if os.path.isdir(os.path.join(folder, n)):
                fails.append("%s: migration folder %s holds a sub-directory %s" % (name, d, n))
            elif n not in ALLOWED_FILES:
                fails.append("%s: migration folder %s holds %s; only %s are allowed"
                             % (name, d, n, ", ".join(ALLOWED_FILES)))
    return listed


def _check_existing_folders(name, base_dir, head_dir, base_mig, fails):
    """Rule 5: a migration folder that exists at base is never modified."""
    base_files = _files(os.path.join(base_dir, "migrations"))
    head_files = _files(os.path.join(head_dir, "migrations"))
    for d in sorted(base_mig):
        prefix = d + os.sep
        touched = sorted(p for p in set(base_files) | set(head_files)
                         if p.startswith(prefix) and base_files.get(p) != head_files.get(p))
        if touched:
            fails.append("%s: existing migration folder %s is modified (%s)"
                         % (name, d, ", ".join(touched)))


def check_module(name, base_dir, head_dir, series, allow_short, fails, warns, out):
    if base_dir is None:
        _check_new_module(name, head_dir, fails, out)
        return
    v_base, v_head = read_version(base_dir), read_version(head_dir)
    out.append("MODULE=" + name)
    out.append("VERSION_BASE=%s" % v_base)
    out.append("VERSION_HEAD=%s" % v_head)
    if v_base is None or v_head is None:
        out.append("BUMP=other")
        out.append("MIGRATION_DIRS_NEW=none")
        out.append("MIGRATION_FILES=none")
        fails.append("%s: manifest version missing or not a string literal" % name)
        return
    b_short, _ = short_form(v_base, series)
    h_short, h_prefixed = short_form(v_head, series)
    if h_prefixed:
        warns.append("%s: version carries the series prefix" % name)
    bump = classify_bump(b_short, h_short)
    out.append("BUMP=" + bump)

    base_mig = set(_migration_dirs(base_dir))
    new_dirs = [d for d in _migration_dirs(head_dir) if d not in base_mig]
    out.append("MIGRATION_DIRS_NEW=" + (",".join(new_dirs) or "none"))

    _check_existing_folders(name, base_dir, head_dir, base_mig, fails)
    listed = _check_new_folders(name, head_dir, new_dirs, h_short, series, allow_short, fails)
    out.append("MIGRATION_FILES=" + (",".join(listed) or "none"))

    if len(new_dirs) > 1:
        fails.append("%s: %d new migration folders (%s); at most one per module"
                     % (name, len(new_dirs), ", ".join(new_dirs)))
    if bump == "other":
        expected = smallest_step(b_short)
        fails.append("%s: version %s -> %s is not the smallest step%s"
                     % (name, b_short, h_short,
                        "; expected " + expected if expected else ""))
    if new_dirs and bump == "none":
        fails.append("%s: a migration folder was added without a version bump" % name)
    if bump == "smallest" and not new_dirs:
        warns.append("%s: version bumped without a migration folder; fine only when the "
                     "change is declared to move existing data or is versioned on purpose" % name)


def run_check(base, head, series, only, allow_short):
    base_mods, head_mods = list_modules(base), list_modules(head)
    fails, warns, out = [], [], []
    for name in (sorted(only) if only else sorted(head_mods)):
        if name not in head_mods:
            warns.append("%s: not present in head, skipped" % name)
            continue
        if not only and name in base_mods and _files(base_mods[name]) == _files(head_mods[name]):
            continue
        check_module(name, base_mods.get(name), head_mods[name], series, allow_short,
                     fails, warns, out)
    for line in out:
        print(line)
    for f in fails:
        print("FAIL_REASON=" + f)
    for w in warns:
        print("WARN=" + w)
    print("MIGRATION_GATE=" + ("FAIL" if fails else "PASS"))
    return 1 if fails else 0


def _csv(value):
    return [p.strip() for p in (value or "").split(",") if p.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="migration_gate.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    c = sub.add_parser("check", help="check a head tree against a base tree")
    c.add_argument("--base", required=True)
    c.add_argument("--head", required=True)
    c.add_argument("--series", required=True)
    c.add_argument("--modules", default="")
    c.add_argument("--allow-short", default="")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 0 if e.code in (0, None) else 3
    if args.cmd != "check":
        ap.print_usage(sys.stderr)
        return 3
    for d in (args.base, args.head):
        if not os.path.isdir(d):
            print("error: not a directory: " + d, file=sys.stderr)
            return 3
    return run_check(args.base, args.head, args.series, _csv(args.modules),
                     set(_csv(args.allow_short)))


if __name__ == "__main__":
    sys.exit(main())
