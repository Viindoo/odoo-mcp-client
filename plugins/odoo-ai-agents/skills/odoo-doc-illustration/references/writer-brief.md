# odoo-doc-illustration - the writer brief

Fill the universal skeleton of `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal
skeleton (read by path) plus the fields below. Every path is the captured absolute literal, never re-resolved by the writer.

## Launch (`odoo-doc-writer`)

```
DISPATCH MODEL: <haiku | sonnet, per concurrency-guard.md § Model-tier selection>
MODE: full
MODULE: <technical name>   MODULE_PATH: <abs path under WORKTREE_PATH>
WORKTREE_PATH: <doc_root>
ODOO VERSION: <series>   PROFILE: <profile | none>
SHARE_DIR: <abs>   ISOLATE_DIR: <abs>   RUN_ID: <id>
INSTANCE_HANDLE: <the odoo-instance block, verbatim>
ADDONS_PATH: <the addons_path returned with it>
LANGUAGES: <resolved list, en_US first>
DOMAIN: <Domain line | none>   SRS: <path | none>
FEATURE CATALOG: <path | none>   ROLE MAP: <path | none>   WALKTHROUGH: <path | none>
CHANGE: <feature list | path of the file holding it | whole | none>
DOC SCOPE: screenshot-doc | full-guide   (full-guide = every catalog row stamped guide | setup | excluded: <reason>)
CAPTURE MODE: screens | scenarios
BROWSER MODE: headless | headed
extends_in_scope: [<base module>, ...]
USER LANGUAGE: <lang | omit>
```

The writer's images live under `static/description/assets/` (the reference gate requires it) and
the cover at the root of `static/description/`: a brief never puts `static/description/` out of the
writer's scope; only `index*.html` there is the marketer's.

## The landing launch (`odoo-marketer`, after `full` returns)

```
DISPATCH MODEL: <haiku | sonnet, per concurrency-guard.md § Model-tier selection>
MODE: landing
MODULE: <technical name>   MODULE_PATH: <abs path under WORKTREE_PATH>
WORKTREE_PATH: <doc_root>
ODOO VERSION: <series>   PROFILE: <profile | none>
SHARE_DIR: <abs>   ISOLATE_DIR: <abs>   RUN_ID: <id>
INSTANCE_HANDLE: <the odoo-instance block, verbatim>
ADDONS_PATH: <the addons_path returned with it>
LANGUAGES: <resolved list, en_US first>
FEATURE CATALOG: <path>   ROLE MAP: <path>   FACTS: <path | none>
STAGED CAPTURES: <the writer's staging directory | none>
MARKETING COPY: <path | none>   BUYER PROFILE: <path | none>   TARGET MARKET: <value | none>
AUTHOR PROFILE: <path of author-profile.json | none>
CHANGE: <feature list | path of the file holding it | whole | none>
BROWSER MODE: headless | headed
extends_in_scope: [<base module>, ...]
USER LANGUAGE: <lang | omit>
```

## A finding to fix (SendMessage to the agent that wrote the file)

```
FINDINGS:
<file>:<line>: <RULE>: <reference>
...
```

## `catalog-only` (launched by `odoo-doc-feature-map`)

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
