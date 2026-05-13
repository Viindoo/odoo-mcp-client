# /odoo-semantic:connect

Interactive command to connect Claude Code to your Odoo Semantic MCP server.

Run this **after** `claude plugin install` because Claude Code v2.1.x has a known
bug where `userConfig` values are never prompted at install time
(github.com/anthropics/claude-code/issues/39455). Without this step the plugin's
`.mcp.json` template cannot resolve and the `odoo-semantic` MCP server silently
fails to load.

## Steps for the AI agent

1. Ask user for MCP server URL. Default: `https://odoo-semantic.viindoo.com:9999/mcp`.
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
   **Do not try to call the MCP tool `resolve_model` here** — Claude Code v2.x
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

5. Tell the user explicitly:
   - `✓ Setup complete. Restart Claude Code to activate the MCP tools.`
   - `After restart, verify with: "Dùng odoo-semantic, resolve model res.partner trên Odoo 17.0"`
   - Then list the 15 skill names shipped by this plugin so the user knows what
     to invoke.

## Hard rules

- Use the `Bash` tool for step 3. Do **not** use `Edit` or `Write` on
  `~/.claude.json` — that file holds unrelated user state (projects, startup
  counters, other MCP servers) and direct edits risk corruption.
- Use the `Bash` tool for step 4. Do **not** attempt to call MCP tool
  `resolve_model` in the same session — it is not yet loaded.
- The API key is sensitive. Mask it (`osm_****`) in any output to the user.
- If the user already has an `odoo-semantic` MCP server registered in a higher
  scope, the plugin's `.mcp.json` template version is suppressed by Claude Code
  dedup rules — this is expected and not an error.
