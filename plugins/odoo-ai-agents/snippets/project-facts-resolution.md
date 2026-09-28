<!-- SSOT snippet. The ordered, terminating ladder Round 0 uses for the four project facts. Edit
     here only; consumers point at ${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md. -->

# Resolve project facts (before you ask)

Every Odoo task needs four facts: the **Odoo series**, the **OSM profile**, the **module/addons
scope**, and - for a live step - an **instance target**. Resolve PER FACT: stop at the rung that
answers one; an unanswered fact keeps descending, answered ones stay authoritative.

## Rung 1 - THE BRIEF

Match brief fields by STEM, any case or separator: series (`VERSION`, `ODOO_VERSION`, `SERIES`,
`odoo_version`), profile (`PROFILE`, `viindoo_profile`), `ADDONS_PATH`, `INSTANCE_HANDLE`,
`SHARE_DIR`, `ISOLATE_DIR`. Use the caller's literal verbatim - a stem the brief answers is
RESOLVED. Re-resolving from your own cwd finds the wrong root across worktrees
(`${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton).

## Rung 2 - THE DECLARED INSTANCE CATALOG

Authoritative for series, profile, addons path, interpreter, DB coordinates, and instance URL.
Call `catalog_locate` with `path` = the repository root (`git rev-parse --show-toplevel`, else the
working directory).

- `matched` true - the returned row is the declared instance whose `addons_path` covers this repo.
  Use its `profile` verbatim for `set_active_profile` - never invent, abbreviate, or suffix a
  profile name. Derive `instance_base_url` per
  `${CLAUDE_PLUGIN_ROOT}/snippets/instance-resolution.md`.
- A key the row omits, or an empty `profile`, answers NOTHING: that fact keeps descending; the
  keys the row does carry stay authoritative. Never hand `set_active_profile` an empty profile -
  name it via OSM `list_available_profiles`, else ask at rung 5.
- `matched` false - nothing declared covers this repo (or no catalog exists): a normal answer, not
  an error. Go to rung 3.
- `CATALOG_UNREADABLE` (the catalog file exists but cannot be parsed) means something IS declared
  and it is broken - report it, never read it as a rung miss and continue quietly.

## Rung 3 - THE CHECKOUT

Authoritative for the series when no instance is declared: call `series_detect` on the repository
root. Only `status` `OK` resolves the series. Full contract:
`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` § Series derivation from a checkout.

- A manifest `version` is NEVER series evidence: it is the addon's own (`1.3`, `1.0.9`) at every
  series, and a code-level upgrade leaves even a series-prefixed value unbumped, so it can name an
  earlier series.
- `NEEDS_CONTEXT` leaves the series UNRESOLVED - carry it to rungs 4-5, treating a step-3
  `hint` as a HYPOTHESIS to confirm there. Never default a series: a wrong one silently
  produces wrong API choices.
- **Module/addons scope:** glob BOTH descriptor filenames (era row 6) - one name misses a whole
  era. Never ask for the module list.

## Rung 4 - THE REQUEST

Use a series, profile, or module the caller stated in their own words this turn.

## Rung 5 - ASK ONCE

Batch every fact still unresolved into ONE message. Ask for nothing a rung above answered.

Edition (Community vs Enterprise) is stored nowhere and is not one of the four facts; settle it per
question with OSM against the resolved series (`list_available_profiles`, `check_module_exists`).
