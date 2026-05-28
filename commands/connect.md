---
name: connect
description: Connect Claude Code to the Odoo Semantic MCP server by registering the server URL and API key, probing reachability, and optionally auto-allowing its tools
---
# /odoo-semantic:connect

Interactive command to connect Claude Code to your Odoo Semantic MCP server.

Run this **after** `claude plugin install` because Claude Code v2.1.x has a known
bug where `userConfig` values are never prompted at install time
(github.com/anthropics/claude-code/issues/39455). Without this step the plugin's
`.mcp.json` template cannot resolve and the `odoo-semantic` MCP server silently
fails to load.

## Steps for the AI agent

1. Ask user for MCP server URL. Default: `https://odoo-semantic.viindoo.com/mcp`.
2. Ask user to paste their API key. Must match `^osm_[A-Za-z0-9_-]+$`.
   Re-prompt on format mismatch. **Do not echo the key back in plain text.**
3. Run the following with the `Bash` tool (substitute `<URL>` and `<KEY>`):
   ```
   claude mcp add --scope user --transport http odoo-semantic <URL> \
     --header "X-API-Key: <KEY>"
   ```
   If `claude mcp add` reports the name already exists, run
   `claude mcp remove odoo-semantic --scope user` first, then retry.
   If exit code is non-zero for any other reason, report stderr to the user and stop.
4. Verify the server is reachable and the key is accepted via HTTP probe.
   **Do not try to call the MCP tool `model_inspect` here** — Claude Code v2.x
   does not hot-reload MCP servers, so `odoo-semantic` is invisible to the AI
   agent until the user restarts the session
   (anthropics/claude-code#46426 — "not planned"). Use `curl` via the `Bash`
   tool instead. Substitute `<URL>` (full URL ending in `/mcp`) and `<KEY>`:
   ```
   BASE_URL=$(echo "<URL>" | sed 's:/mcp/*$::')
   curl -sfo /dev/null "${BASE_URL}/health" \
     || { echo "✗ Server unreachable at ${BASE_URL}/health"; exit 1; }
   STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
     -H "X-API-Key: <KEY>" "${BASE_URL}/mcp")
   case "$STATUS" in
     401|403) echo "✗ API key rejected (HTTP $STATUS)"; exit 1 ;;
     *)       echo "✓ Server reachable, key accepted (HTTP $STATUS)" ;;
   esac
   ```
   The MCP endpoint returns 401/403 only for missing or invalid keys. A valid
   key reaches the FastMCP handler, which responds 200/202/405/406 to a plain
   GET — any of those is success for the purposes of this probe.
   - On `✓`: continue to step 5.
   - On `✗`: surface the curl output and stop. Common fixes: VPN/firewall,
     server restarted with server-side key rotation, key revoked on the server.

5. Offer to auto-allow every `mcp__odoo-semantic__*` tool in the user-scope
   permissions file so the user is not prompted on every tool call. Plugin
   manifests cannot declare permissions themselves
   ([plugin `settings.json` only accepts `agent` + `subagentStatusLine`](https://code.claude.com/docs/en/plugins)),
   so this is the only safe automated path.

   Ask the user: `Auto-allow every mcp__odoo-semantic__* tool in ~/.claude/settings.json? [Y/n]`.
   Default `Y`. If the user answers `n` / `no` / `skip`, skip to step 6 and
   tell them they can re-run `/odoo-semantic:connect` later, or paste the
   snippet from `docs/setup.md#claude-code-auto-trust` manually.

   On `Y`, run the following exact block with the `Bash` tool. It edits
   `~/.claude/settings.json` (NOT `~/.claude.json`), preserves every other key,
   refuses to overwrite an invalid-JSON file, backs up before writing, and is
   idempotent (re-running adds nothing). **Copy the fenced block verbatim
   without re-indenting** — Python is whitespace-sensitive and the heredoc
   body must start at column 0.

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
        print(f"✗ {p} is not valid JSON ({e}). Refusing to overwrite.", file=sys.stderr)
        sys.exit(2)
    shutil.copy2(p, f"{p}.bak.{int(time.time())}")
perms = data.setdefault("permissions", {})
allow = perms.setdefault("allow", [])
entry = "mcp__odoo-semantic"
if entry in allow:
    print(f"✓ {entry} already in allow-list — no change.")
    sys.exit(0)
allow.append(entry)
os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
with open(p, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
print(f"✓ Added {entry} to permissions.allow in {p}.")
PY
```

   On exit code 2 (invalid JSON): surface the stderr line to the user verbatim
   and stop. Do **not** retry, do **not** delete the file. Suggest they fix
   `~/.claude/settings.json` by hand (or restore from a `.bak.*` copy) and
   re-run `/odoo-semantic:connect`.

   On exit code 0: continue to step 6.

6. Tell the user explicitly:
   - `✓ Setup complete. Restart Claude Code to activate the MCP tools.`
   - `After restart, verify with: "Use odoo-semantic, model_inspect sale.order on Odoo 17.0"`
   - If step 5 ran successfully, also: `Auto-allow is on — no more per-tool permission prompts for odoo-semantic.`
   - Then list the 15 skill names shipped by this plugin so the user knows what
     to invoke.

## Hard rules

- Use the `Bash` tool for step 3. Do **not** use `Edit` or `Write` on
  `~/.claude.json` — that file holds unrelated user state (projects, startup
  counters, other MCP servers) and direct edits risk corruption.
- Use the `Bash` tool for step 4. Do **not** attempt to call MCP tool
  `model_inspect` in the same session — it is not yet loaded.
- Use the `Bash` tool for step 5. Do **not** use `Edit` or `Write` on
  `~/.claude/settings.json` directly — it may hold the user's other permission
  rules, hooks, and statusLine config. The Python snippet above is the only
  approved path: it backs up, refuses to corrupt invalid JSON, and is
  idempotent. Do **not** substitute `jq` (not guaranteed to be installed on
  the user's machine).
- `~/.claude/settings.json` (permissions/hooks) and `~/.claude.json` (MCP
  server registry) are different files. Step 3 writes to the latter via
  `claude mcp add`; step 5 writes to the former via the Python snippet. Do not
  cross the streams.
- The API key is sensitive. Mask it (`osm_****`) in any output to the user.
- If the user already has an `odoo-semantic` MCP server registered in a higher
  scope, the plugin's `.mcp.json` template version is suppressed by Claude Code
  dedup rules — this is expected and not an error.
