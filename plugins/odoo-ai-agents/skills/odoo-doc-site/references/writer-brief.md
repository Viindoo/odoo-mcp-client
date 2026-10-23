# odoo-doc-site - the writer brief

Fill the universal skeleton of `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal
skeleton (read by path) plus the fields below. Every path is the captured absolute literal.

## Launch (`odoo-doc-site-writer`)

```
DISPATCH MODEL: sonnet | haiku
SITE WORKTREE: <abs path of the series worktree>
SERIES: <series>   PROFILE: <profile part of the series' instance key | none>
LANGUAGES: <site languages, source first>
PAGE PLAN: <abs path of page-plan.md>   GROUP: <group id>
FACTS: <abs path of the group's facts file, then the catalog / role map / walkthrough paths>
INSTANCE HANDLE: <the odoo-instance block, verbatim | none provisioned>
ADDONS_PATH: <the addons_path returned with it>
DOCS PYTHON: <abs path of the docs venv python recorded in step 0>
SHARE_DIR: <abs>   ISOLATE_DIR: <abs>   RUN_ID: <id>
POLICY: <abs path of <RUN_DIR>policy.json>
REPO FACTS: <abs path of <RUN_DIR>repo-facts.json>
CONTENT WIDTH: <content_width of the content-width record | none>   SERVED URLS: <language: base URL | none>
FROM CHANGE: <abs path of the change file | none>
USER LANGUAGE: <lang | omit>
```

Required: `SITE WORKTREE`, `SERIES`, `LANGUAGES`, `PAGE PLAN`, `FACTS`, `INSTANCE HANDLE`,
`DOCS PYTHON`, `SHARE_DIR`, `ISOLATE_DIR`, `POLICY`, `REPO FACTS`. `FACTS` is one file per group,
`<SHARE_DIR>/docs-site/<site>/<series>/facts/<area>.<group>.md`; no two writers share a file. `CONTENT WIDTH` is `none` only for the
`check-shot` launch, which gets `SERVED URLS` to measure it; every other launch gets the recorded
value and `none` for `SERVED URLS`.

`DISPATCH MODEL`: `sonnet` when the group has a `compose` or `port` row; `haiku` when every row is
`recapture`, `relabel`, `wire`, `fill` or `check-shot`. Tier table:
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Model-tier selection.

## Work kinds in the page plan

| `work` | The writer does |
|---|---|
| `compose` | researches, writes the RST, captures, installs images, fills the translation |
| `recapture` | recaptures the listed shots at the existing size; no prose change |
| `relabel` | corrects UI terms and alt text to the instance; no new prose |
| `wire` | adds the toctree entries and cross-references; no new prose |
| `fill` | fills existing `.po` entries from the module translations and the reused terms |
| `port` | the page was merged into the worktree from the row's `source_series` by `odoo-forward-port`: re-verifies, adapts, recaptures every image, regenerates and fills the translation |
| `check-shot` | captures the one screen per language of `check-shot.md`, measures the content width; writes no page |

## A finding to fix (SendMessage to the same writer)

```
FINDINGS:
<file>:<line>: <GATE>: <message>
...
```

## What comes back

The status word first, then the pages written (paths), images, translation entries, facts gaps,
findings, `UNKNOWN`s, and the Continuation Contract block. A `check-shot` launch returns the
image paths, `reference_viewport` and `content_width`.
