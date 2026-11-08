"""Where Claude Code keeps its settings files, in precedence order.

Imports `os` only, so a per-prompt hook can load it in a few milliseconds.
"""
import os


def config_dir_path():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def user_settings_path(config_dir):
    return os.environ.get("CLAUDE_SETTINGS") or os.path.join(config_dir, "settings.json")


def settings_files(config_dir, cwd):
    """(scope, path) in Claude Code's precedence order, highest first (managed is out of reach)."""
    return [
        ("local", os.path.join(cwd, ".claude", "settings.local.json")),
        ("project", os.path.join(cwd, ".claude", "settings.json")),
        ("user", user_settings_path(config_dir)),
    ]
