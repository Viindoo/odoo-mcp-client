# odoo-code-review - dispatch briefs

Fill the universal skeleton of `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal
skeleton (read by path) plus the fields below. Inputs only; the reviewer's body owns every
procedure. Launch parameters, never brief lines: the `model` each heading names and `effort` per
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Effort.

## R1 - mechanical pass (`odoo-code-reviewer`, model haiku)

```
MODE: R1
TARGET: <abs path of the tree> <BASE>..<HEAD>
CHANGED_SET: <repo-relative paths, one per line>   DIFF_PATH: <path | none>
SOURCE_DIFF_PATH: <path | none>   (a port only)
ODOO VERSION: <version>   PROFILE: <profile | none>
SHARE_DIR: <abs>   ISOLATE_DIR: <abs>   RUN_ID: <id>
DOMAIN: <Domain line | none>
RECON: <path | none>   IMPACT_MAP: <path | none>
RUN_MODULES: <modules earlier nodes of the run changed | omit>
USER LANGUAGE: <lang | omit>
```

## R2 - behaviour and verdict (`odoo-code-reviewer`, model sonnet)

```
MODE: R2
TARGET, CHANGED_SET, DIFF_PATH, SOURCE_DIFF_PATH, ODOO VERSION, PROFILE, SHARE_DIR, ISOLATE_DIR, RUN_ID, DOMAIN: <as R1>
R1_FINDINGS: <the R1 report path; in a plan run one per build node>
R3_FINDINGS: <path | none>
SRS: <path | none>   DESIGN_DOC: <path | none>   MASTER_DESIGN_DOC: <path | none>
RECON: <path | none>   IMPACT_MAP: <path | none>
UI_REVIEW: <ISOLATE_DIR>/reviews/<slug>-<date>/ui-review-<module>.md | none
INSTANCE_HANDLE: <handle | none>
USER LANGUAGE: <lang | omit>
```

## R3 - specialist pass (`odoo-code-reviewer`, model opus; only when due)

```
MODE: R3
TARGET, CHANGED_SET, DIFF_PATH, SOURCE_DIFF_PATH, ODOO VERSION, PROFILE, SHARE_DIR, ISOLATE_DIR, RUN_ID, DOMAIN: <as R1>
R1_FINDINGS: <path>
SRS: <path | none>   DESIGN_DOC: <path | none>   MASTER_DESIGN_DOC: <path | none>
RECON: <path>
USER LANGUAGE: <lang | omit>
```

## A resumed round (SendMessage to the same reviewer)

Triage, R2 only (`${CLAUDE_PLUGIN_ROOT}/snippets/fix-round.md` § 1):

```
ACCEPTANCE_EVIDENCE: <acceptance report path | none>
UI_REVIEW: <ui review report path | none>
```

Verifying a fix (§ 4 of that file; R1 verifies its own findings with `PRIOR_FINDINGS`):

```
ROUND: <n>
PRIOR_FINDINGS: <that reviewer's earlier report path>
FIX_DIFF: <the diff file of the fix: the coder returns it; a caller that commits itself has git-ops write it>
IMPACT_MAP: <updated path>
```

## UI reviewer (`odoo-ui-reviewer`, model sonnet; when an instance exists and views changed)

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
