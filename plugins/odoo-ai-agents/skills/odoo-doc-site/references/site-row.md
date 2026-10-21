# odoo-doc-site - the site row

The machine-local file `${ODOO_AI_HOME:-$HOME/.odoo-ai}/docs-sites.toml` holds one `[[site]]` row
per documentation repository. Read the row; never copy a value of it into a file that is
committed.

## Pick the row

`SITE` matches the row `key`; else the row whose `remote` identifies the repo the user named. No
row, or several candidates: `NEEDS_CONTEXT` naming `/odoo-ai-agents:odoo-setup docs-site`.

## What each part decides

| Row part | Used for |
|---|---|
| `remote` | the upstream the PR targets and the branch each series starts from |
| `fork_remote` | where the branch is pushed |
| `languages` | the site languages, source language first; the capture instance loads all of them and every page is translated into every non-source one |
| `audience` | the readers; passed to the writer as the audience of every page |
| `repos` | optional; the code repositories the site documents, stated by the operator |
| per-series table | `clone` (a local checkout of the docs repo; at least one series declares one, and a worktree of any series is made from any of them; read facts from it, never write it), `instance` (a catalog `instance_key`, `<series>:<profile>`; it names the capture instance, its series and its profile), `extra_modules` (installed on the capture instance next to the area's modules), `module_bridge_patterns` (names of bridge modules to add for every app the plan shows) |
| `policy.banned_terms`, `banned_terms_exempt_paths` | wording the site never publishes, and the paths where it may appear; checked by `content_gates.py` in text and in the capture-text log of the images |
| `policy.forbid_version_prose` | no series number written in prose |
| `policy.marketplace_url` | the link pattern with `{series}` and `{module}`; filled with the worktree's own series |
| `policy.site_url_prefix` | prefix of the public URL of a page; builds the URLs in the plan and the PR body |
| `policy.demo_company` | the main company's name per language; the writer sets it on the capture database before capturing that language (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/doc-capture-mechanics.md` § 15) |
| `policy.forward_port_branch_pattern` | optional; the branch name of an automatic forward port, with `{pr}` and `{series}`; absent means no such automation, `port.md` |
| `policy.commit` | `one-per-pr` or `per-area`, step 7 |
| `policy.check_shot` | when the check shot runs: `first-per-series` (no content-width record yet) or `always`, `check-shot.md` |
| `policy.semantic_classes` | the only emphasis classes a page may use |

## Resolved values travel as values

Pass the writer the path of `<RUN_DIR>policy.json` as `POLICY` and the path of `<RUN_DIR>repo-facts.json` as
`REPO FACTS` (`SKILL.md` step 0); the writer never reads the site row.
