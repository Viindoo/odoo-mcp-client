# odoo-code-review - dispatch briefs

Fill the universal skeleton of `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal
skeleton (read by path) plus the fields below. Inputs only; the reviewer's body owns every
procedure.

## R1 - mechanical pass (`odoo-code-reviewer`, model haiku)

Launch parameters, not brief lines: `model` = haiku; `effort` per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Effort.

```
MODE: R1
TARGET: <abs path of the tree> <BASE>..<HEAD>
CHANGED_SET: <repo-relative paths, one per line>   DIFF_PATH: <path | none>
ODOO VERSION: <version>   PROFILE: <profile | none>
SHARE_DIR: <abs>   ISOLATE_DIR: <abs>   RUN_ID: <id>
DOMAIN: <Domain line | none>
RECON: <path | none>   IMPACT_MAP: <path | none>
USER LANGUAGE: <lang | omit>
```

## R2 - behaviour and verdict (`odoo-code-reviewer`, model sonnet)

Launch parameters, not brief lines: `model` = sonnet; `effort` per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Effort.

```
MODE: R2
TARGET, CHANGED_SET, DIFF_PATH, ODOO VERSION, PROFILE, SHARE_DIR, ISOLATE_DIR, RUN_ID, DOMAIN: <as R1>
R1_FINDINGS: <ISOLATE_DIR>/reviews/<slug>-<date>/r1-findings.md
R3_FINDINGS: <path | none>
SRS: <path | none>   DESIGN_DOC: <path | none>   MASTER_DESIGN_DOC: <path | none>
RECON: <path | none>   IMPACT_MAP: <path | none>
UI_REVIEW: <ISOLATE_DIR>/reviews/<slug>-<date>/ui-review-<module>.md | none
INSTANCE_HANDLE: <handle | none>
USER LANGUAGE: <lang | omit>
```

## R3 - specialist pass (`odoo-code-reviewer`, model opus; only when due)

Launch parameters, not brief lines: `model` = opus; `effort` per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Effort.

```
MODE: R3
TARGET, CHANGED_SET, DIFF_PATH, ODOO VERSION, PROFILE, SHARE_DIR, ISOLATE_DIR, RUN_ID, DOMAIN: <as R1>
R1_FINDINGS: <path>
SRS: <path | none>   DESIGN_DOC: <path | none>   MASTER_DESIGN_DOC: <path | none>
RECON: <path>
USER LANGUAGE: <lang | omit>
```

## A later round (SendMessage to the same reviewer)

```
ROUND: <n>
PRIOR_FINDINGS: <that reviewer's earlier report path>
FIX_DIFF: <BASE>..<HEAD> of the fix
IMPACT_MAP: <updated path>
ACCEPTANCE_EVIDENCE: <acceptance report path | none>   (R2 only)
```

## UI reviewer (`odoo-ui-reviewer`, model sonnet; when an instance exists and views changed)

Launch parameters, not brief lines: `model` = sonnet; `effort` per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Effort.

```
USER LANGUAGE: <lang>
ODOO_VERSION: <version>
SLUG: <slug>-<date>
SHARE_DIR: <abs>   ISOLATE_DIR: <abs>
SCREENS: <view, action and menu xml_ids from CHANGED_SET, of module <module>>
INSTANCE_HANDLE: <handle>
DESIGN_DOC: <path | none>   MOCKUPS: <paths | none>
ARTIFACT_FILE: <ISOLATE_DIR>/reviews/<slug>-<date>/ui-review-<module>.md
Return a short summary (per-section PASS/WARN/FAIL + top finding) and the artifact path.
```
