# odoo-doc-illustration - the writer brief

Fill the universal skeleton of `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal
skeleton (read by path) plus the fields below. Inputs only; the writer's body owns every
procedure. Every path is the captured absolute literal, never re-resolved by the writer.

## Launch (`odoo-doc-writer`, model sonnet)

```
DISPATCH MODEL: sonnet
MODE: full | landing
MODULE: <technical name>   MODULE_PATH: <abs path under WORKTREE_PATH>
WORKTREE_PATH: <doc_root>
ODOO VERSION: <series>   PROFILE: <profile | none>
SHARE_DIR: <abs>   ISOLATE_DIR: <abs>   RUN_ID: <id>
INSTANCE_HANDLE: <the odoo-instance block, verbatim>
ADDONS_PATH: <the addons_path returned with it>
LANGUAGES: <resolved list, en_US first>
DOMAIN: <Domain line | none>   SRS: <path | none>
FEATURE CATALOG: <path | none>   ROLE MAP: <path | none>   WALKTHROUGH: <path | none>
MARKETING COPY: <path | none>   BUYER PROFILE: <path | none>   TARGET MARKET: <value | none>
DOC SCOPE: screenshot-doc | full-guide
CAPTURE MODE: screens | scenarios
BROWSER MODE: headless | headed
extends_in_scope: [<base module>, ...]
USER LANGUAGE: <lang | omit>
```

## The landing round (SendMessage to the same writer after `full`)

```
MODE: landing
MARKETING COPY: <path | none>   BUYER PROFILE: <path | none>   TARGET MARKET: <value>
```

## A finding to fix (SendMessage)

```
FINDINGS:
<file>:<line>: <RULE>: <reference>
...
```

## `catalog-only` (launched by `odoo-doc-feature-map` and `odoo-doc-walkthrough`)

```
DISPATCH MODEL: sonnet
MODE: catalog-only
MODULE: <technical name>   MODULE_PATH: <abs path>
WORKTREE_PATH: <abs path of the checkout holding the module>
ODOO VERSION: <series>   PROFILE: <profile | none>
SHARE_DIR: <abs>   ISOLATE_DIR: <abs>   RUN_ID: <id or slug>
FEATURE CATALOG: <path | none>   ROLE MAP: <path | none>   WALKTHROUGH: <path | none>
USER LANGUAGE: <lang | omit>
```
