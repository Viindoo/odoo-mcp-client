<!-- SSOT snippet: the documentation that closes a code change - a forward-port, an upgrade or a
     plan's docs nodes. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/docs-after-change.md. -->

# Documentation after a change

Runs once the change's PR is presented, for the target the approved plan's `Docs:` line names
(`none`: nothing runs). Under that approved plan it presents no gate.

**One capture instance for the whole tail.** A documentation step never builds an instance
another step of the same run already built. The caller forwards, as `INSTANCE_HANDLE`, the
demo build it already holds - the `odoo-i18n` export instance returned under `HAND_ON`, or the
handle the previous docs step returned - when that build covers the step (its `addons_path`
covers the worktree, `demo` is true, `languages_loaded` holds every documentation language, the
series matches); the step installs any missing module on that lease by a delta `init` through
`odoo-instance` and never takes a second lease. The caller, as the run-level owner, releases the
handle once the last docs step returned (`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md`
T1); a docs step releases only a lease it took itself.

1. **The change file.** Write `<ISOLATE_DIR>/docs/change-<slug>.md`: one line per added, changed
   or removed user-visible feature, with its module and its UI label or menu path. A module that
   is `installable: False` on the target series has no line: its `doc/` and `static/description/`
   land exactly as the change carried them, with no rewrite and no recapture.
2. **Module docs** (`module` or `both`): invoke `odoo-doc-illustration` on the change's worktree
   with `CHANGE` = the change file (every layer the module ships: the user guide and the App Store
   page) and the forwarded `INSTANCE_HANDLE` when one covers it, then commit its files onto the
   SAME open PR's branch through `git-toolkit:git-ops` - one PR per repo per run. Its return names
   the handle it used.
3. **Site docs** (`site` or `both`): invoke `odoo-doc-site` with `CODE_WORKTREE` = the change's
   worktree, `SERIES` = the target series, `FROM CHANGE` = the change file and the handle step 2
   returned (else the forwarded one) as `INSTANCE_HANDLE`. It lands its own PR on the docs
   repository.
4. **Release** the forwarded handle (`lease_release` with its token and the run id) once the last
   step returned.
