#!/usr/bin/env python3
"""skill_listing.py - measure Claude Code's skill listing and decide its budget (stdlib only).

Every turn Claude Code shows the model ONE listing of the model-invocable skills and commands of
the session: its own bundled skills, every enabled plugin's, the user's and the project's. Each
entry is ``- <name>: <description>[ - <when_to_use>]``. The listing is capped at a fraction of the
context window; over the cap Claude Code keeps every name and drops the descriptions of the
least-used entries (bundled skills are never cut), so the model can still invoke those skills but
rarely chooses one on its own.

Counting (read from Claude Code's listing builder, CLI v2.1.x):

  budget      = floor(context_window_tokens * CHARS_PER_TOKEN * skillListingBudgetFraction)
                (the environment variable SLASH_COMMAND_TOOL_CHAR_BUDGET replaces it when set)
  entry chars = len(name) + 4 + min(len(text), PER_ENTRY_TEXT_CAP)
                text = description, or "description - when_to_use" when both exist
  listing     = sum(entry chars) + one newline between consecutive entries

An entry with ``disable-model-invocation: true`` is not listed; a ``skillOverrides`` value of
``"off"`` or ``"user-invocable-only"`` hides it, ``"name-only"`` lists the name only.

Bundled skills live inside the CLI binary, so their cost cannot be read from disk. When a CLI
debug log holds a "Skill listing over budget" line that describes the CURRENT state, that line
is the measurement of the WHOLE listing (bundled included) and wins. A line describes the current
state only when it was written after every input that shapes the listing last changed (the
settings files, the installed-plugin record, each enabled plugin's install, the user's and the
project's skill dirs) and in a session of THIS project (its "Loading skills from" line names this
project's skills dir). Such a line was logged under the fraction in force now, so the window it
implies is sound. Anything else - a line from before a raise, before a plugin update, or from
another project - is ignored, and the bundled part is the observation below.

Subcommands (all read-only except ``set``):
  measure [--window TOKENS] [--cwd DIR]   KEY=VALUE facts about the listing and the decision
  set <settings.json> <fraction>          write skillListingBudgetFraction (backup, refuse bad JSON)
"""
import glob
import json
import math
import os
import re
import shutil
import sys
import time

# Claude Code's defaults (see the module docstring).
DEFAULT_FRACTION = 0.01
CHARS_PER_TOKEN = 4
PER_ENTRY_TEXT_CAP = 1536
DEFAULT_WINDOW_TOKENS = 200_000

# Observation, not a rule: the bundled skills' share of the listing, counted from the skill
# listing a live session sent the model (CLI 2.1.288, 2026-10). It depends on the account's
# enabled features (5,318 and 5,549 chars were seen on the same CLI version) and changes between
# CLI versions; the larger value is kept so the estimate errs towards "overflows".
BUNDLED_OBSERVED_CHARS = 5_549
BUNDLED_OBSERVED_CLI = "2.1.288"

# A proposed budget leaves this share free above the measured listing, so one more skill does
# not tip it over again; fractions are rounded up to this step.
PROPOSAL_HEADROOM = 0.10
FRACTION_STEP = 0.005

OVER_BUDGET_RE = re.compile(
    r"Skill listing over budget: (\d+) skills, (\d+) chars > (\d+) budget"
)
LOADING_SKILLS_RE = re.compile(r"Loading skills from: .*?project=\[([^\]]*)\]")
LINE_TIME_RE = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?)(Z|[+-]\d\d:?\d\d)?")


# --------------------------------------------------------------------------- #
# frontmatter + counting
# --------------------------------------------------------------------------- #
def parse_frontmatter(text):
    """Top-level scalar keys of a leading --- block (inline values and >/| block scalars)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out = {}
    i = 1
    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            return out
        if line and not line[0].isspace() and ":" in line:
            key, _, val = line.partition(":")
            val = val.strip()
            if val in (">", "|", ">-", "|-", ">+", "|+"):
                body = []
                j = i + 1
                while j < len(lines) and lines[j].strip() != "---" and (
                    lines[j].strip() == "" or lines[j][:1].isspace()
                ):
                    body.append(lines[j].strip())
                    j += 1
                sep = "\n" if val.startswith("|") else " "
                out[key.strip()] = sep.join(b for b in body if b).strip()
                i = j
                continue
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]
            out[key.strip()] = val
        i += 1
    return out


def listing_text(fm):
    desc = str(fm.get("description") or "").strip()
    when = str(fm.get("when_to_use") or "").strip()
    return f"{desc} - {when}" if when else desc


def is_hidden(fm):
    return str(fm.get("disable-model-invocation", "")).strip().lower() == "true"


def entry_chars(listed_name, fm, override=None):
    """Chars one entry adds, or None when it is not listed."""
    if is_hidden(fm) or override in ("off", "user-invocable-only"):
        return None
    if override == "name-only":
        return len(listed_name) + 2
    return len(listed_name) + 4 + min(len(listing_text(fm)), PER_ENTRY_TEXT_CAP)


def listing_total(entry_sizes):
    sizes = [s for s in entry_sizes if s is not None]
    return sum(sizes) + max(0, len(sizes) - 1)


def budget_chars(window_tokens, fraction):
    return int(math.floor(window_tokens * CHARS_PER_TOKEN * fraction))


# --------------------------------------------------------------------------- #
# discovery on disk
# --------------------------------------------------------------------------- #
def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _md_entries(paths, prefix, overrides):
    sizes = []
    for path in paths:
        try:
            fm = parse_frontmatter(open(path, encoding="utf-8").read())
        except OSError:
            continue
        base = os.path.basename(os.path.dirname(path)) if os.path.basename(path) == "SKILL.md" \
            else os.path.splitext(os.path.basename(path))[0]
        name = fm.get("name") or base
        listed = f"{prefix}:{name}" if prefix else name
        sizes.append(entry_chars(listed, fm, overrides.get(listed, overrides.get(name))))
    return sizes


def plugin_entry_sizes(plugin_root, overrides=None):
    """Listing entry sizes of one installed plugin directory."""
    overrides = overrides or {}
    manifest = _read_json(os.path.join(plugin_root, ".claude-plugin", "plugin.json")) or {}
    name = manifest.get("name") or os.path.basename(plugin_root.rstrip("/"))
    skills_dir = os.path.join(plugin_root, manifest.get("skills") or "skills")
    skill_files = sorted(glob.glob(os.path.join(skills_dir, "*", "SKILL.md")))
    cmds = manifest.get("commands")
    if isinstance(cmds, list):
        cmd_files = [os.path.normpath(os.path.join(plugin_root, c)) for c in cmds]
    else:
        cmd_files = sorted(glob.glob(os.path.join(plugin_root, cmds or "commands", "*.md")))
    return _md_entries(skill_files + cmd_files, name, overrides)


def settings_files(config_dir, cwd):
    """(scope, path) in Claude Code's precedence order, highest first (managed is out of reach)."""
    return [
        ("local", os.path.join(cwd, ".claude", "settings.local.json")),
        ("project", os.path.join(cwd, ".claude", "settings.json")),
        ("user", user_settings_path(config_dir)),
    ]


def user_settings_path(config_dir):
    return os.environ.get("CLAUDE_SETTINGS") or os.path.join(config_dir, "settings.json")


def config_dir_path():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def _merged_setting(config_dir, cwd, key):
    """(value, scope) of the highest-precedence settings file that sets `key`, else (None, None)."""
    for scope, path in settings_files(config_dir, cwd):
        data = _read_json(path)
        if isinstance(data, dict) and key in data:
            return data[key], scope
    return None, None


def _enabled_plugins(config_dir, cwd):
    enabled = {}
    for _scope, path in reversed(settings_files(config_dir, cwd)):
        data = _read_json(path)
        if isinstance(data, dict) and isinstance(data.get("enabledPlugins"), dict):
            enabled.update(data["enabledPlugins"])
    return [k for k, v in enabled.items() if v]


def _install_path(registry, key, cwd):
    entries = ((registry or {}).get("plugins") or {}).get(key) or []
    best = None
    for e in entries:
        if e.get("scope") in ("project", "local") and e.get("projectPath") != cwd:
            continue
        best = e.get("installPath") or best
    return best


def measure_on_disk(config_dir, cwd):
    """Chars of the plugin, user and project parts of the listing, read from installed files."""
    overrides = {}
    for _scope, path in reversed(settings_files(config_dir, cwd)):
        data = _read_json(path)
        if isinstance(data, dict) and isinstance(data.get("skillOverrides"), dict):
            overrides.update(data["skillOverrides"])
    registry = _read_json(os.path.join(config_dir, "plugins", "installed_plugins.json"))
    plugin_sizes = []
    for key in _enabled_plugins(config_dir, cwd):
        root = _install_path(registry, key, cwd)
        if root and os.path.isdir(root):
            plugin_sizes += plugin_entry_sizes(root, overrides)
    user = sorted(glob.glob(os.path.join(config_dir, "skills", "*", "SKILL.md"))
                  + glob.glob(os.path.join(config_dir, "skills", "synced", "*", "SKILL.md"))
                  + glob.glob(os.path.join(config_dir, "commands", "*.md")))
    project = sorted(glob.glob(os.path.join(cwd, ".claude", "skills", "*", "SKILL.md"))
                     + glob.glob(os.path.join(cwd, ".claude", "commands", "*.md")))
    return {
        "plugins": listing_total(plugin_sizes),
        "user": listing_total(_md_entries(user, None, overrides)),
        "project": listing_total(_md_entries(project, None, overrides)),
    }


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def listing_inputs(config_dir, cwd):
    """Every file or dir whose change can change the listing; their newest mtime is the moment
    the listing last changed shape."""
    paths = [path for _scope, path in settings_files(config_dir, cwd)]
    paths.append(os.path.join(config_dir, "plugins", "installed_plugins.json"))
    registry = _read_json(os.path.join(config_dir, "plugins", "installed_plugins.json"))
    for key in _enabled_plugins(config_dir, cwd):
        root = _install_path(registry, key, cwd)
        if root:
            paths.append(root)
    for base in (config_dir, os.path.join(cwd, ".claude")):
        paths += [os.path.join(base, "skills"), os.path.join(base, "commands")]
    return paths


def _line_time(line, fallback):
    m = LINE_TIME_RE.match(line)
    if not m:
        return fallback
    stamp = m.group(1) + (m.group(2) or "Z").replace("Z", "+00:00")
    try:
        from datetime import datetime
        return datetime.fromisoformat(stamp).timestamp()
    except ValueError:
        return fallback


def _same_project(text, cwd):
    want = os.path.realpath(os.path.join(cwd, ".claude", "skills"))
    for listed in LOADING_SKILLS_RE.findall(text):
        for path in listed.split(","):
            path = path.strip()
            if path and os.path.realpath(path) == want:
                return True
    return False


def latest_debug_measurement(config_dir, cwd, not_before):
    """(skills, chars, budget) from the newest over-budget line that describes the current state:
    written after `not_before` (the newest listing input) by a session of project `cwd`.
    None when no line qualifies."""
    best = None
    for path in glob.glob(os.path.join(config_dir, "debug", "*.txt")):
        file_time = _mtime(path)
        if file_time is None or file_time <= not_before:
            continue
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if not _same_project(text, cwd):
            continue
        for line in text.splitlines():
            m = OVER_BUDGET_RE.search(line)
            if not m:
                continue
            when = _line_time(line, file_time)
            if when > not_before and (best is None or when >= best[0]):
                best = (when, tuple(int(x) for x in m.groups()))
    return best[1] if best else None


# --------------------------------------------------------------------------- #
# decision
# --------------------------------------------------------------------------- #
def propose_fraction(listing_chars, window_tokens):
    need = listing_chars * (1 + PROPOSAL_HEADROOM) / (window_tokens * CHARS_PER_TOKEN)
    steps = math.ceil(round(need / FRACTION_STEP, 9))
    return min(1.0, round(steps * FRACTION_STEP, 3))


def decide(listing_chars, window_tokens, current_fraction=None, current_scope=None,
           env_budget=None):
    """What setup should do about the listing budget. Pure: no I/O.

    Returns a dict with `action` one of:
      fits          the listing already fits its budget - nothing to do
      env-override  SLASH_COMMAND_TOOL_CHAR_BUDGET fixes the budget; a setting would be ignored
      scope-override a project/local setting decides the fraction; the user file cannot raise it
      propose       ask the user to set `fraction` in the user settings file

    A proposal is always above the fraction in force: it is only made when the listing overflows
    the current budget, and the proposed budget holds the listing, so setup never lowers a value.
    """
    fraction_now = DEFAULT_FRACTION if current_fraction is None else float(current_fraction)
    budget_now = int(env_budget) if env_budget else budget_chars(window_tokens, fraction_now)
    out = {
        "listing_chars": listing_chars,
        "window_tokens": window_tokens,
        "fraction_now": fraction_now,
        "budget_now": budget_now,
        "listing_tokens": math.ceil(listing_chars / CHARS_PER_TOKEN),
    }
    if listing_chars <= budget_now:
        return dict(out, action="fits")
    if env_budget:
        return dict(out, action="env-override")
    proposed = propose_fraction(listing_chars, window_tokens)
    if current_scope in ("local", "project"):
        return dict(out, action="scope-override", fraction=proposed)
    shown_now = min(listing_chars, budget_now)
    out.update(
        action="propose",
        fraction=proposed,
        budget_new=budget_chars(window_tokens, proposed),
        extra_tokens=math.ceil((listing_chars - shown_now) / CHARS_PER_TOKEN),
        window_share_pct=round(100.0 * listing_chars / (window_tokens * CHARS_PER_TOKEN), 1),
    )
    return out


def measure(window_tokens=None, cwd=None, config_dir=None, environ=None):
    """Measure the session's listing and decide. Returns the decide() dict plus provenance."""
    environ = os.environ if environ is None else environ
    config_dir = config_dir or config_dir_path()
    cwd = cwd or os.getcwd()
    current, scope = _merged_setting(config_dir, cwd, "skillListingBudgetFraction")
    env_budget = environ.get("SLASH_COMMAND_TOOL_CHAR_BUDGET") or None
    newest_input = max((m for m in map(_mtime, listing_inputs(config_dir, cwd)) if m), default=0)
    debug = latest_debug_measurement(config_dir, cwd, newest_input)
    disk = measure_on_disk(config_dir, cwd)
    if debug:
        _skills, chars, logged_budget = debug
        source = "cli-debug-log"
        # The line postdates every settings file, so it was logged under the fraction in force now.
        fraction_then = DEFAULT_FRACTION if current is None else float(current)
        if window_tokens is None and not env_budget:
            window_tokens = int(round(logged_budget / (CHARS_PER_TOKEN * fraction_then)))
        bundled = None
    else:
        parts = [disk["plugins"], disk["user"], disk["project"], BUNDLED_OBSERVED_CHARS]
        chars = sum(parts) + sum(1 for p in parts if p) - 1
        source = f"files+bundled-observed-on-cli-{BUNDLED_OBSERVED_CLI}"
        bundled = BUNDLED_OBSERVED_CHARS
    window_tokens = window_tokens or DEFAULT_WINDOW_TOKENS
    result = decide(chars, window_tokens, current, scope, env_budget)
    result.update(source=source, plugins_chars=disk["plugins"], user_chars=disk["user"],
                  project_chars=disk["project"], bundled_chars=bundled,
                  current_scope=scope or "default")
    return result


# --------------------------------------------------------------------------- #
# write
# --------------------------------------------------------------------------- #
def set_fraction(settings_path, fraction):
    """Set skillListingBudgetFraction in one settings file. Exit codes: 0 ok, 2 refused."""
    data = {}
    if os.path.exists(settings_path):
        data = _read_json(settings_path)
        if not isinstance(data, dict):
            print(f"refusing to edit {settings_path}: not a JSON object", file=sys.stderr)
            return 2
        shutil.copy2(settings_path, f"{settings_path}.bak.{time.strftime('%Y%m%d%H%M%S')}")
    data["skillListingBudgetFraction"] = fraction
    os.makedirs(os.path.dirname(settings_path) or ".", exist_ok=True)
    tmp = f"{settings_path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, settings_path)
    return 0


def _main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]
    if cmd == "measure":
        window = cwd = None
        while args:
            flag = args.pop(0)
            if flag == "--window":
                window = int(args.pop(0))
            elif flag == "--cwd":
                cwd = args.pop(0)
        for key, val in measure(window, cwd).items():
            print(f"{key.upper()}={'' if val is None else val}")
        return 0
    if cmd == "set" and len(args) == 2:
        return set_fraction(args[0], float(args[1]))
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
