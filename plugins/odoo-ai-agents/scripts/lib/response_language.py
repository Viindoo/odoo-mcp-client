#!/usr/bin/env python3
"""Print the response language Claude Code is configured with, or nothing.

Claude Code keeps it in the settings key `language` (a free string); hooks do not receive it and
no environment variable carries it, so this reads the settings files, highest precedence first:
managed settings, the project's `.claude/settings.local.json`, the project's
`.claude/settings.json`, then the user's `settings.json` (`CLAUDE_CONFIG_DIR` relocates
`~/.claude`). Inside a git worktree the project files live at the main checkout root, so both the
working directory and that root are tried.

Usage: response_language.py [PROJECT_DIR]     (default: the current directory)
Prints the value on one line, or nothing. Never fails: an unreadable or malformed file is skipped.
Stdlib only; nothing but the `language` value is ever printed.
"""
import json
import os
import sys

_MANAGED_DIRS = ("/etc/claude-code", "/Library/Application Support/ClaudeCode")


def _main_checkout(project):
    """The main checkout root when `project` is inside a linked git worktree, else None."""
    d = os.path.abspath(project)
    while True:
        dot_git = os.path.join(d, ".git")
        if os.path.isfile(dot_git):
            try:
                with open(dot_git, encoding="utf-8") as fh:
                    line = fh.read().strip()
                if line.startswith("gitdir:"):
                    gitdir = line[len("gitdir:"):].strip()
                    if not os.path.isabs(gitdir):
                        gitdir = os.path.join(d, gitdir)
                    gitdir = os.path.normpath(gitdir)
                    # <main>/.git/worktrees/<name>
                    parent = os.path.dirname(os.path.dirname(gitdir))
                    if os.path.basename(parent) == ".git":
                        return os.path.dirname(parent)
            except (OSError, UnicodeDecodeError):
                pass
            return None
        if os.path.isdir(dot_git):
            return None
        up = os.path.dirname(d)
        if up == d:
            return None
        d = up


def _candidates(project):
    managed_override = os.environ.get("CLAUDE_MANAGED_SETTINGS_DIR")
    for d in ([managed_override] if managed_override else list(_MANAGED_DIRS)):
        yield os.path.join(d, "managed-settings.json")
    roots = [project]
    main = _main_checkout(project)
    if main and os.path.abspath(main) != os.path.abspath(project):
        roots.append(main)
    for name in ("settings.local.json", "settings.json"):
        for root in roots:
            yield os.path.join(root, ".claude", name)
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    yield os.path.join(config_dir, "settings.json")


def effective_language(project):
    for path in _candidates(project):
        try:
            with open(path, encoding="utf-8") as fh:
                value = json.load(fh).get("language")
        except (OSError, ValueError, UnicodeDecodeError, AttributeError):
            continue
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())[:64]
    return ""


def main(argv):
    try:
        value = effective_language(argv[1] if len(argv) > 1 else os.getcwd())
    except Exception:  # never fail a session
        value = ""
    if value:
        print(value)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
