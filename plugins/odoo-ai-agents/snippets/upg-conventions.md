# Upgrade conventions

Apply every convention below on every profile and distribution, OSM-reachable or not. The
`odoo-modules-upgrade` P4 adapt dispatch brief (`upg-phase-detail.md` § odoo-coding dispatch brief)
cites this file.

---

## Convention 1 - No version bump on code-level upgrade

When upgrading a module's code to a new Odoo series (§ Convention 0) with no behavior contract
change visible to end users, do **not** bump `version` in `__manifest__.py` and do **not** add the
series prefix.

- Keep the existing short form `x.y.z` unchanged. A value carrying the series prefix
  (`<series>.x.y.z`) is CONVERTED to `x.y.z` by dropping the prefix - a conversion is not a bump.
  Form SSOT: `${CLAUDE_PLUGIN_ROOT}/snippets/new-module-manifest.md §3`.

> Convention 1 applies to upgrade commits only; forward-port sets the version by
> `[[fp-merge-absorption]]` C1.

---

## Convention 3 - Always-invisible field carries an XML comment

Full rule, definition and enforcing test, per series:
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/coding_guidelines/<series>/xml.md` § Always-invisible field carries a comment.
The enforcing test is a framework class a module-scoped `--test-tags` run skips unless it is
named: `odoo-instance-ops` unions it into every test run that installs a module with view XML
(`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § Framework-validation test classes),
so a missing comment fails the P5 install + test gate on a series that ships the class.

---

## Convention 4 - `hr.employee` fields absent from `hr.employee.public` need `groups=` (from v16)

Full rule and code example:
`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` section "Core test-enforced authoring rules".

The rule is stated in the `hr.employee` model docstring - read it there for the target series.
Omitting the `groups=` fails the `hr` self-access check in the P5 install + test gate, on the
series that ship it.

---

## Convention 0 - A series upgrade is a CODE upgrade (UPG), never a database migration (MIG)

Governs every P4 adapt of `odoo-modules-upgrade`.

**UPG.** Input: a module's source on series N. Output: its source on the target series, which
installs on a FRESH database of the target series, passes its tests and acceptance, keeps its
business behaviour and is modernised as if newly developed there - newest mechanisms (API, views,
frontend framework, manifest, tests), no compatibility layer for an older series, no deprecated
API, a module absorbed by core deleted. It writes no migration script, deletes the `migrations/`
directory of every upgraded module, never touches, restores or updates an existing database, keeps
no old field or xmlid name for data compatibility and never asks how existing data will be
migrated. What a later MIG project needs, including every deleted `migrations/` directory, goes
into `migration-notes.md` (`odoo-modules-upgrade` § P7).

**MIG.** Moving an existing database's data to a higher series. The plugin only writes code for it
(module-level migration scripts through `odoo-data-migration`, when the user asks separately) and
never executes it. Never a step of UPG.

**Wording.** "Migration script" = a module-level `migrations/` script; "database migration (MIG)" =
the database move; moving code to a newer framework mechanism = "modernisation" (UPG).

**Commit tag.** A commit request for upgrade work proposes the commit convention's series-upgrade
tag (`[UPG]`), never the migration tag.

**(b) Write the target series' newest mechanism, not a shim.** The P2 NEW-FEATURE SWEEP already
recorded any replacement in `reuse_candidates[]`
(`${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/upg-phase-detail.md` § P2 step 3b);
do NOT re-run it. A feature WITH an entry -> implement the target-core mechanism it names and
delete the custom implementation; WITHOUT one -> nothing to do. Never wrap the new mechanism in a
compatibility shim over the old one.

**(c) Bias to the newest external API, decidably.** Trigger the vendor-currency pass when EITHER holds:
1. the module's `__manifest__.py` declares `external_dependencies` with at least one non-empty list
   under `python` or `bin`; OR
2. the module imports a top-level package that is neither `odoo`, nor the module's own name, nor a
   relative import, nor in the running interpreter's stdlib set
   (`python3 -c 'import sys; print("\n".join(sorted(sys.stdlib_module_names)))'`).

Cannot decide whether a name is stdlib -> treat as TRIGGERED. When triggered: for each distinct
third-party package, ONE bounded `WebFetch` or `WebSearch` per
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md` § Tier 2 (official upstream) - no follow-up
chain - capped at THREE packages per module, ONE network call each.

**Then ACT on the finding, do not merely record it.** When the pass shows the module uses an API the
upstream package has superseded: write the NEWEST upstream API in the adapted code and record
`vendor_api_checked: <pkg>@<found> -> adapted-to <newest>`. When the newest API would require a
behavior change beyond this upgrade's scope, keep the current call, record
`vendor_api_checked: <pkg>@<found> (newer <newest> deferred - <one-line reason>)`, and surface that
line at the P6 gate. Never silently keep a superseded call. Other outcomes, one of exactly these:
`vendor_api_checked: <pkg>@<version-found>` (already current);
`vendor_api_checked: over-cap (<n> packages)`; `vendor_api_checked: not-triggered`;
`vendor_api_checked: unreachable`. This pass is ADVISORY and never blocks the adapt. Record it as the
reserved `vendor_api_checked:` field of THIS module's `absorption/<module>.md` (schema:
`${CLAUDE_PLUGIN_ROOT}/skills/odoo-modules-upgrade/references/upg-phase-detail.md` § P2 output
FORMAT) - the same file the P6 gate presents, satisfying the "surface at P6" rule above without a
separate step.
