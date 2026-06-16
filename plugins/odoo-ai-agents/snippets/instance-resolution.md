# Instance profile resolution (where `instances.toml` lives)

`instances.toml` declares the local Odoo instances on THIS host - series,
`http_port`, `db_host`/`db_user`/`db_name`, `addons_path`, and the venv `python`.
It is **machine-global**, not project-scoped: an execute-agent has no guaranteed
working directory, so the instance profile must be findable from any cwd. (Every
other `.odoo-ai/` artifact - `context.md`, `survey/`, `worklog/`, ... - stays
project-scoped under `./.odoo-ai/`.)

## Resolution order (stop at the first that yields a usable instance)

1. **`instance_base_url` in `./.odoo-ai/context.md`** - a project may pin a
   specific running instance for its own work; this project override wins when present.
2. **`$ODOO_AI_INSTANCES`** - an explicit full path to an `instances.toml`
   (set in the environment; used by tests / non-standard layouts).
3. **`$HOME/.odoo-ai/instances.toml`** - the machine-global profile written by
   `/odoo-ai-agents:odoo-setup`. This is the canonical source; prefer it.
4. **`./.odoo-ai/instances.toml`** - a project-local profile, only as a
   transitional fallback when no machine-global file exists yet.

Read a profile with the shipped reader (it emits shell-eval-able `INST_*` lines):

```
python3 <plugin>/scripts/lib/instances_io.py read <path-to-instances.toml> [series]
```

The first `[[instance]]` whose `series` matches (or the highest `X.Y` when no
series is requested) is the active instance; its `http_port` gives
`instance_base_url = http://localhost:<http_port>`. If none of the sources above
yields an instance, surface a single clarifying request for the instance URL
rather than guessing.
