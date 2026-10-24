---
name: connect
argument-hint: "[optional: server-url]"
description: Connect Claude Code to the Odoo Semantic MCP server - set its URL and key through the plugin's configuration and check it responds
---
# /odoo-semantic-mcp:connect

Connects this Claude Code to your Odoo Semantic MCP server. The plugin already declares the
server (`.mcp.json`) and the two values it needs (`userConfig`: the server URL and the key); this
command gets them filled in the right place, removes what hides the plugin's server, and verifies
the connection. Nothing sensitive goes through the chat: Claude Code's own configuration dialog
stores the key.

## Steps for the AI agent

1. **Is the plugin's server hidden by an older registration?** Run with the `Bash` tool:
   ```
   claude mcp get odoo-semantic 2>&1 | head -5
   ```
   A line `Scope: User` (or `Local` / `Project`) means a stand-alone `odoo-semantic` entry was
   registered by hand earlier; Claude Code lets it SHADOW the plugin's server of the same name,
   so a value filled in the plugin dialog would never be used. Tell the operator this, and ask
   (one closed question) whether to remove that entry so the plugin's server takes over; on yes
   run `claude mcp remove odoo-semantic --scope <that scope>`; on no, stop - the stand-alone
   entry stays theirs to manage.

2. **The values.** Tell the operator, in their language:
   - the server URL: the default `https://odoo-semantic.viindoo.com/mcp` serves most; a
     self-hosted server has its own (`$ARGUMENTS` when given: pass it on as the URL to enter);
   - where to put them: open `/plugin`, choose `odoo-semantic-mcp`, **Configure**, and fill in
     "MCP Server URL" and "API Key" - a masked dialog stored by Claude Code itself. In a terminal
     the same is `claude plugin configure odoo-semantic-mcp@viindoo-plugins --values-stdin`
     with a JSON object of the two options on stdin (the plugin id is what `claude plugin list`
     shows). The key comes from your server admin or https://odoo-semantic.viindoo.com/install/.
   - then `/reload-plugins` (or a new session).
   You never ask for the key, never receive it in chat, never write it anywhere.

3. **Verify the connection from THIS session** once the operator says the dialog is done and the
   plugins were reloaded: call the MCP tool `mcp__odoo-semantic__list_available_versions` with no
   arguments.
   - A list comes back: connected. Say so, with the versions it names.
   - The tool is not available: the reload has not happened (MCP servers do not hot-reload a new
     server; a reload re-reads the plugin's configuration) - ask for `/reload-plugins`, else a
     new session, and verify again.
   - An authentication error: the key was refused - the operator re-opens the dialog and re-enters
     it (a key is rotated on the server side at times).
   - Another error: the server is unreachable (VPN, firewall, a self-hosted server that is down);
     report the message as it is.

4. **Auto-allow the server's tools** (so no prompt on every call). Ask once:
   `Allow every Odoo Semantic tool without a prompt, in your user settings? (approve / cancel)`.
   On approve run the following exact block with the `Bash` tool - it edits
   `~/.claude/settings.json` (NOT `~/.claude.json`), keeps every other key, refuses an
   invalid-JSON file, backs up before writing, and is idempotent. **Copy the fenced block
   verbatim without re-indenting.**

```bash
SETTINGS="$HOME/.claude/settings.json"
python3 - "$SETTINGS" <<'PY'
import json, os, sys, time, shutil
p = sys.argv[1]
data = {}
if os.path.exists(p):
    try:
        with open(p) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"x {p} is not valid JSON ({e}). Refusing to overwrite.", file=sys.stderr)
        sys.exit(2)
    shutil.copy2(p, f"{p}.bak.{int(time.time())}")
perms = data.setdefault("permissions", {})
allow = perms.setdefault("allow", [])
entry = "mcp__odoo-semantic"
if entry in allow:
    print(f"ok {entry} already in allow-list - no change.")
    sys.exit(0)
allow.append(entry)
os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
with open(p, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
print(f"ok Added {entry} to permissions.allow in {p}.")
PY
```
   Exit 2: surface the stderr line and stop; do not retry or delete anything.

5. **Report**: connected or not, the tools allowed or not, and the one thing left for the
   operator when something is still missing.

## Why the values are not registered by this command

A value typed in the chat lands in the session transcript on disk, and a value passed on a
command line lands in the shell history and the process list. The plugin's `userConfig` dialog
is the one path Claude Code masks and stores itself; the plugin's `.mcp.json` reads it as
`${user_config.api_key}` and `${user_config.mcp_url}`. Plugin servers reload on
`/reload-plugins`; a brand-new stand-alone registration needs a new session.
