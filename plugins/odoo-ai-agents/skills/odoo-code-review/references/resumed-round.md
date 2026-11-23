# A resumed review round

For `odoo-code-reviewer` when its brief carries `ACCEPTANCE_EVIDENCE`, `UI_REVIEW`, `FIX_DIFF` or
`PRIOR_FINDINGS`. The round it serves: `${CLAUDE_PLUGIN_ROOT}/snippets/fix-round.md`.

## Triage (`R2`: `ACCEPTANCE_EVIDENCE` or `UI_REVIEW`, no `FIX_DIFF`)

Rewrite the `## Fix list` of `review.md`. Put every acceptance FAIL, every tester observation and
every UI finding under the item whose cause explains it, or open a new item; one cause is one
item, however many places show it. Set each item's `origin` on evidence:

- `code` - lines of the diff produce it: cite them;
- `pre-existing` - the lines that produce it stand outside the diff, in a module the change
  touches;
- `platform` - core or a module the change does not touch produces it: the tester's
  `reproduces without module: yes`, or the source line that shows who owns the behaviour (the
  groups of a menu, an access rule, a core control);
- `oracle` - the scenario's expected value contradicts the SRS, or assumes platform behaviour
  the platform does not have and the SRS does not ask for;
- `msgid` - a source string, not its translation, is wrong;
- `environment` - the instance, the data or the browser. Before naming it for a UI symptom, list
  every template patch the changed modules make on that component (`t-inherit`, `inherit_id`)
  and exclude each by evidence; the item carries that list.

A symptom that does not reproduce without the change is never `platform`, whoever owns the
screen. An item whose cause you cannot read in the source is `cause: hypothesis`, with what
would prove it; it still carries the `origin` the evidence so far points to, marked provisional.

## Verify (`FIX_DIFF`)

`R2`: for each item of the fix list rule `closed` (the new line), `open` (why) or `withdrawn` (the
coder's evidence it was not a defect). Read only the lines the fix wrote: a new finding there is
written only when CRITICAL or HIGH, marked `introduced by the fix`; anything else goes to a `debt`
list. `R1` (`PRIOR_FINDINGS`): re-run only the checks of the earlier findings on the changed files.
