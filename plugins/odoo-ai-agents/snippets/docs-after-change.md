<!-- SSOT snippet: the documentation that closes a code change - a forward-port, an upgrade or a
     plan's docs nodes. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/docs-after-change.md. -->

# Documentation after a change

Runs once the change's PR is presented, for the target the approved plan's `Docs:` line names
(`none`: nothing runs). Under that approved plan it presents no gate.

1. **The change file.** Write `<ISOLATE_DIR>/docs/change-<slug>.md`: one line per added, changed
   or removed user-visible feature, with its module and its UI label or menu path. A module that
   is `installable: False` on the target series has no line: its `doc/` and `static/description/`
   land exactly as the change carried them, with no rewrite and no recapture.
2. **Module docs** (`module` or `both`): invoke `odoo-doc-illustration` on the change's worktree
   with `CHANGE` = the change file (every layer the module ships: the user guide and the App Store
   page), then commit its files onto the SAME open PR's branch through `git-toolkit:git-ops` - one
   PR per repo per run.
3. **Site docs** (`site` or `both`): invoke `odoo-doc-site` with `CODE_WORKTREE` = the change's
   worktree, `SERIES` = the target series, `FROM CHANGE` = the change file. It lands its own PR on
   the docs repository.
