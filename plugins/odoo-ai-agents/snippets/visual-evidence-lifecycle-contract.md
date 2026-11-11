# Run-scoped state: slug and retention

Where each path sits (SHARE or ISOLATE) is in
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; this file says how a run names its
per-run paths and who deletes them.

## Clause 1 - one collision-proof slug per run

Use the `SLUG:` of your brief when it carries one. Otherwise mint the slug once, at the start of
the run, before any path that embeds it:

```
<intent-slug>-<YYYYMMDD>-<4 random chars>
```

Take the four characters from a real command, never from your own reasoning - two agents reasoning
about the same intent are not independent samples:

```bash
printf '%02x%02x' $((RANDOM % 256)) $((RANDOM % 256))
```

Reuse that one value for every path the run touches: no fresh slug per screen, module or step, and
never the literal `<slug>` token in a path. The same shape names a demo recording
(`visual/videos/<feature>-<YYYYMMDD>-<4 random chars>.{mp4,gif}`; a before/after pair shares one
value and appends `-before` / `-after`) and the id of a `run-<id>.json`.

## Clause 2 - the four evidence directories under `visual/`

Each owner sweeps its own directory at its Phase or Round 0, before it mints its own slug, and
never a sibling's:

```
find <ISOLATE_DIR>/visual/<subdir>/ -mindepth 1 -maxdepth 1 -type d -mmin +<minutes> -exec rm -rf {} +
```

| Directory | Owner | Kept |
|---|---|---|
| `visual/current/<slug>/` | `odoo-visual-regression` | deleted by its own run at its terminal status; 24h (1440) for a crashed run |
| `visual/qa/<slug>/<module>/` | `odoo-acceptance` | 30 days (43200): it is the evidence a verdict cites |
| `visual/debug/<slug>/` | `odoo-debug` | 30 days |
| `visual/screenshots/<slug>/` | `odoo-ui-review` | 30 days |

A live run keeps writing into its own directory, so the age test never matches it.

## Clause 3 - every other run-scoped path

The same rule: the owner sweeps its own path at its Phase 0, before creating this run's own.

| Path (under `<ISOLATE_DIR>`) | Owner | Kept |
|---|---|---|
| `worklog/<run-or-slug>/` | the first writer of a run (`worklog-contract.md`) | 30 days |
| `git-rebase/<slug>/`, `forward-port/<slug>/`, `modules-upgrade/<slug>/` | the skill of that name | 30 days |
| `coding/<slug>-<date>/`, `reviews/<slug>-<date>/`, `i18n/<slug>-<date>/` | `odoo-coding`, `odoo-code-review`, `odoo-i18n` | 30 days |
| `pr-monitoring/<id>.md`, `followups/<slug>.md`, `visual/videos/*` (files: `-type f`) | `odoo-pr-monitoring`, the follow-up command, `odoo-demo-recording` | 30 days |
| a workflow's `output_dir` | `workflow-chaining`, once, for the active workflow | 30 days |
| `visual/<run_id>/<module>_staging/` | `odoo-doc-illustration` | deleted at the end of its run; 24h for a crashed run. Its sweep runs on `visual/` itself, so it excludes every named sibling (`baselines`, `doc`, `current`, `qa`, `debug`, `screenshots`, `videos`, `adhoc`) by name |
| `integration/<slug>/` | the plan runner | § 3.6 |

Never swept by a skill:

- `run-<id>.json` - a run paused at a human gate is still alive however old its file is.
- `recon/<slug>-<date>/` - kept (`scouting-persistence-contract.md`).
- `brainstorm/state.json` - one file, overwritten.
- `visual/adhoc/<slug>/` - the plugin runtime prunes it after 30 days.
- Every SHARE path (baselines, the doc cache, designs, plans, surveys, the documentation cache):
  its value is surviving across runs; the consumer checks staleness when it reads.
- Tier-1 `logs/` and `conf/` - reclaimed by the instance tools, by age and lease reachability.

### 3.6 - `integration/<slug>/` is deleted on the run's status, not on age alone

A run can wait at a human gate for any length of time, so age proves nothing here. A directory
older than 24h is deleted only when the run file of the same id says the RUN itself is terminal
(`DONE`, `BLOCKED` or `NEEDS_CONTEXT`), read as the JSON root's `status` with `jq` - the file
also holds a `status` per node, which a text match cannot tell apart. No run file, unreadable
JSON, an empty status, `NEEDS_NEXT`, or no `jq`: skip, never delete. The command is at
`plan-mode-schema.md` § Running the plan, Run start.
