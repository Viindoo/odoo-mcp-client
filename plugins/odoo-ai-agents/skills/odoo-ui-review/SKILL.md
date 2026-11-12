---
name: odoo-ui-review
argument-hint: "[screen/view to review]"
description: >-
  Rates how a rendered Odoo screen looks and behaves in a live browser
---

## Role

Front door of the `odoo-ui-reviewer` agent: has rendered Odoo screens rated against
`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-ui-contract.md` and, when the design gives them, its
acceptance criteria and mockups. Serves the user who asks how a screen looks, and a plan's
`ui-review` node after a change that touches a screen. Every finding cites what the browser showed.

## Out of Scope

- **Why a screen is broken, errors or renders blank** -> `odoo-debug`
- **Two states or builds compared for drift** -> `odoo-visual-regression`
- **A workflow driven across roles with a PASS/FAIL verdict** -> `odoo-acceptance`
- **A demo or walkthrough video** -> `odoo-demo-recording`
- **Writing or changing the screen** -> `odoo-coding`
- **Source-level review** -> `odoo-code-review`

## Dispatch

1. **Paths and slug.** Resolve `<SHARE_DIR>` and `<ISOLATE_DIR>` once
   (`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`), sweep this skill's evidence
   directory and then mint one `SLUG`
   (`${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md` Clauses 2 and 1).
2. **Instance.** An `INSTANCE_HANDLE` in the request is passed on and never released here. A
   request with `SELF_PROVISION: worktree-addons` (a plan's tail node): build ONE database with
   demo data from `WORKTREE_PATH` holding `MODULES`, through `Skill(odoo-instance)`, pass its
   handle, and release that lease after the reviewer returns. Neither: the running instance per
   `${CLAUDE_PLUGIN_ROOT}/snippets/instance-resolution.md`.
3. **What to review.** `SCREENS`: the screen the user named, or the views, actions and menus the
   change touched. `ROLE`: the role the screen serves, with its groups. `ROLE_LOGIN`: a login of that role
   the request names; `create` when step 2 built the database; else omitted. `DESIGN_DOC`: the one the request names;
   else the newest file under `<SHARE_DIR>/designs/`; in a master-child design the child path of
   the module from `index.yaml`, plus `MASTER_DESIGN_DOC`
   (`${CLAUDE_PLUGIN_ROOT}/snippets/master-child-design-contract.md`). `MOCKUPS`: the mockup
   paths the design names, or `none`.
4. **Launch `odoo-ui-reviewer`** (`model: sonnet`) with those values, the captured `SHARE_DIR`
   and `ISOLATE_DIR`, `SLUG`, `ODOO_VERSION` and `USER LANGUAGE`
   (`${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton). Add
   `BROWSER MODE: headed` only when the human asked to watch the browser and a display is
   available. The reviewer returns findings and edits nothing: a fix goes to `odoo-coding`.

## Standalone-first fallback

- **OSM unreachable or the module not indexed:** the reviewer grounds the screen from the tree
  (`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`) and labels its report.
- **No instance and none can be built:** review the screenshots the caller already holds and say
  so; with none, return `NEEDS_NEXT` with `next: odoo-instance` (`operation: ensure-up`, the
  series, the modules), or `BLOCKED` when provisioning is impossible. Never ask for a URL or a
  screenshot to be pasted.

## Continuation Contract

Append the block of `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`: `produced` = the
report path and the evidence directory; `status: DONE` with the verdict.
