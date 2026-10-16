# odoo-debug - the debugger brief

Fill the universal skeleton of `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal
skeleton (read by path) plus the fields below. Inputs only; the debugger's body owns the method.

## Launch (`odoo-backend-debugger` or `odoo-ui-debugger`)

```
DISPATCH MODEL: sonnet | opus | fable
SYMPTOM: <one line, then the traceback or console text verbatim>
REPRODUCTION: <the smallest stable recipe from triage | unknown>
SUSPECTED_LAYER: backend | ui
MODULES: <module names in scope, one per line>
WORKTREE_PATH: <abs path of the checkout under edit | none>
ODOO_VERSION: <concrete series>   PROFILE: <profile | none>
SLUG: <the session slug>
SHARE_DIR: <abs>   ISOLATE_DIR: <abs>   RUN_ID: <id | none>
INSTANCE_HANDLE: <handle | none>              # ui: the instance to drive
BROWSER MODE: headless | headed               # ui only
PRIOR_FINDINGS: <the earlier report path | none>   # an escalated tier: verify, do not repeat
USER LANGUAGE: <lang | omit>
```
