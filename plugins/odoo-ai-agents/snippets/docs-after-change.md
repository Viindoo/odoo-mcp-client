# Documentation after a change

Runs after acceptance, the fix round and the i18n reconcile, and before the change's push and
pull request, so one push carries the code, the docs and the URLs of the videos they embed. Its
target is the one the approved plan's `Docs:` line names (`none`: nothing runs); under that plan
it presents no gate. Whoever proposes a target other than `none` runs the reference gate of
`${CLAUDE_PLUGIN_ROOT}/snippets/module-doc-references.md` on each touched module first and writes
the count of findings on the `Docs:` line: a doc file the step edits is brought into the
convention as a whole, so that count is the size of the step.

**A product defect seen while documenting** is reported by the writer, the marketer or the video
producer as a finding. The caller sends it through its own fix loop before the push, then has
only the shots and scenes that show what the fix changed taken again.

**One capture instance per build shape.** Module docs show the module alone (auto-install
skipped); site docs show the product as users run it (auto-install on), and an update never adds
the auto-install modules an earlier build skipped. So the module-docs step reuses the demo build
the caller already holds - the `odoo-i18n` export instance returned under `HAND_ON` - when it
covers the step (its `addons_path` covers the worktree, `demo` is true, `languages_loaded` holds
every documentation language, the series matches), installing any missing module on that lease by
a delta `init` through `odoo-instance`; the site-docs step builds its own instance and takes its
own shots, with the module guide's walkthrough and figures as its shot list. The caller, as the
run-level owner, releases a forwarded handle once the module-docs step returned
(`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1); a docs step releases only a
lease it took itself.

1. **The change file.** Write `<ISOLATE_DIR>/docs/change-<slug>.md`: one line per added, changed
   or removed user-visible feature, with its module and its UI label or menu path. A module that
   is `installable: False` on the target series has no line: its `doc/` and `static/description/`
   land exactly as the change carried them, with no rewrite and no recapture.
2. **Module docs** (`module` or `both`): invoke `odoo-doc-illustration` on the change's worktree
   with `CHANGE` = the change file (every layer the module ships: the user guide and the App Store
   page), `VIDEO` = the watch URLs of the videos the run uploaded, and the forwarded
   `INSTANCE_HANDLE` when one covers it, then commit its files on the change's branch through
   `git-toolkit:git-ops`. Its return names the handle it used.
3. **Release** the forwarded handle (`lease_release` with its token and the run id) once step 2
   returned, or at once when there is no step 2.
4. **Site docs** (`site` or `both`): invoke `odoo-doc-site` with `CODE_WORKTREE` = the change's
   worktree, `SERIES` = the target series and `FROM CHANGE` = the change file. It builds and
   releases its own capture instance and lands its own PR on the docs repository.

## Where a video goes

The publication and embedding rules of a video a run produced are
`${CLAUDE_PLUGIN_ROOT}/snippets/video-destination.md`. A video for a channel is uploaded
`unlisted` once its deliverable passed its checks, with no confirmation
(`${CLAUDE_PLUGIN_ROOT}/snippets/planning-gate-contract.md` rule 4), so its URL is there for
step 2.
