# odoo-content-draft - the marketer brief

Fill the universal skeleton of `${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal
skeleton (read by path) plus the fields below. Every path is the captured absolute literal.

## Launch (`odoo-marketer`, `MODE: copy`)

```
DISPATCH MODEL: <haiku | sonnet | opus, per concurrency-guard.md § Model-tier selection>
MODE: copy
CHANNEL: <linkedin | blog | youtube-script | email-sequence | landing-page-copy | social-caption>
TOPIC: <the subject or product angle>
AUDIENCE: <the named audience | none>   TONE: <variant | none>   OUTPUT LANGUAGE: <lang>
MODULE: <technical name | none>   MODULE_PATH: <abs path | none>
ODOO VERSION: <series | none>   PROFILE: <profile | none>
SHARE_DIR: <abs>   ISOLATE_DIR: <abs>   RUN_ID: <id | none>
FEATURE CATALOG: <path | none>   ROLE MAP: <path | none>   FACTS: <path | none>
BUYER PROFILE: <path | none>   TARGET MARKET: <value | none>
USER LANGUAGE: <lang | omit>
```

Required: `MODE`, `CHANNEL`, `TOPIC`, `SHARE_DIR`, `ISOLATE_DIR`. `MODULE` and its facts travel
whenever the topic is a module. The agent returns the draft, its saved path and `concerns`.

## A revision (SendMessage to the same agent)

```
REVISE: <what to change, in the user's words>
```
