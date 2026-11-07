# Preflight: Gate #1 and Gate #2

Run the gates BEFORE listing the plan or touching any file. They make no changes.

**Gate #1 - Odoo Semantic MCP connection.** Confirm it is reachable in THIS session.
- Authoritative check (AI-level): try calling the MCP tool
  `mcp__plugin_odoo-semantic-mcp_odoo-semantic__list_available_versions` with no arguments (fallback:
  `mcp__plugin_odoo-semantic-mcp_odoo-semantic__cli_help`). This call, not a shell probe, is the source of truth.
  - Responds normally → connected. Continue to Gate #2.
  - Tool is "not found" / unavailable → the server is not loaded in this
    session. **Stop setup and make no changes.** Tell the user: run
    `/odoo-semantic-mcp:connect`, then `/reload-plugins` (the plugin's server reloads
    with its configuration; only a server registered by hand needs a new session), then
    re-run `/odoo-ai-agents:odoo-setup`.
  - Tool returns a 401 / auth error → Stop and suggest re-running
    `/odoo-semantic-mcp:connect`.
  - Tool returns some other error (server down, self-hosted instance offline)
    → this is a server issue, not a session issue. You MAY continue with a
    clear warning that indexed-codebase grounding will be unavailable until
    the server is back.
- Shell fallback: `00-osm-gate.sh check` confirms the server is registered in
  `~/.claude.json` and its `/health` endpoint answers. Use it only as a
  secondary signal (e.g. non-interactive runs); the tool call above is authoritative.
- Filter-aware: for `all` and `instance`, Gate #1 is a HARD block (those
  flows need the backend). For browser-only filters (`browser`, `runtime`,
  `permissions`) it is a SOFT warning - the user may proceed.

**Gate #2 - Host prerequisites.** Only after Gate #1 passes. Skip this gate
entirely for `permissions` and `runtime` (they only edit config files).
- Run `SETUP_FILTER=<filter> "$STEPS_DIR/05-prereq-check.sh" apply [--version X.Y] [--profile P]`
  (the run's own `--version` / `--profile`, when given) and read the checklist.
- Every REQUIRED item present: continue without asking - the plan lists what was found.
- A REQUIRED item missing: stop before the plan with the item in the operator's words and the
  fix the checklist prints ("PostgreSQL is not answering on this machine - start it, or tell
  me where it runs"); when only the instance goal is blocked, offer to go on with the other
  goals and leave the instance for a later run.
- The two "cannot be auto-detected" boxes of the checklist are not questions: the build
  dependencies are checked by the venv build itself, and a declared venv by the venv gate
  below.
- **Venv hard-gate.** For every DECLARED source-mode instance in `instances.toml`, the
  checklist verifies the instance's `python` field is populated AND
  `<python> <odoo-bin> --version` actually runs. A source-mode instance with no working venv
  is a REQUIRED item shown missing: the gate reports FAILED with remediation
  (`45-venv.sh create-venv --series <X.Y> --profile <name>`, or point the `python` field at
  an existing venv) and setup does not proceed for that instance. Setting
  `ODOO_AI_ALLOW_NO_VENV=1` downgrades this specific check from FAILED to a printed WARN.
