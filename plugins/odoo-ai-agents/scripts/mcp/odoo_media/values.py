"""values.py - the configured values this server receives, by environment variable NAME.

The plugin's .mcp.json maps each `${user_config.<option>}` onto one of these names. A value that
is absent, empty, or still the literal placeholder (the option was never set, so Claude Code passed
the text through) counts as NOT configured. Only presence (a boolean) ever leaves this module in a
tool result; `require()` hands the value to the library call and nowhere else.
"""

import os

from odoo_local.errors import ToolError

SPEECH = "SPEECH_API_KEY"
YT_CLIENT_ID = "YOUTUBE_CLIENT_ID"
YT_CLIENT_SECRET = "YOUTUBE_CLIENT_SECRET"
YT_SLOTS = ("docs", "marketing", "third")
YT_TOKEN = dict((slot, "YOUTUBE_REFRESH_TOKEN_%s" % slot.upper()) for slot in YT_SLOTS)

# environment variable name -> the plugin option (plugin.json userConfig) the operator fills in
OPTION = {SPEECH: "speech_api_key", YT_CLIENT_ID: "youtube_client_id", YT_CLIENT_SECRET: "youtube_client_secret"}
for _slot in YT_SLOTS:
    OPTION[YT_TOKEN[_slot]] = "youtube_refresh_token_%s" % _slot


def present(name):
    value = os.environ.get(name, "")
    return bool(value) and not value.startswith("${")


def require(name):
    if not present(name):
        option = OPTION[name]
        raise ToolError("VALUE_NOT_CONFIGURED", "the plugin option '%s' is not set" % option,
                        {"option": option})
    return os.environ[name]


def presence():
    """{option: bool} for every value this server can receive."""
    return dict((OPTION[name], present(name)) for name in OPTION)
