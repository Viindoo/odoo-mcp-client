# Fix round

How the findings of review, acceptance and UI review become one fix by the coder that built the
node. It binds whoever owns the round: the plan runner at its `fix-round` node, a skill that
resumes its coder, the main agent after a standalone review.

## 1. Collect every gate, then triage once

No fix starts while a gate of the change is still running. When review R2, acceptance and UI
review have all returned, resume R2 once (`SendMessage`) with the acceptance report and the UI
review: it rewrites the `## Fix list` of `review.md`
(`${CLAUDE_PLUGIN_ROOT}/skills/odoo-code-review/references/resumed-round.md`). With neither
report, the fix list R2 already wrote stands. A round driven by one report alone (a debug
diagnosis, a CI failure, a port's own review) has that report as its fix list.

Each item is one cause with the findings, bugs and UI findings it explains:

| `origin` | The item goes |
|---|---|
| `code` - the change causes it, its tests included | to the coder |
| `pre-existing` - proved in a module the change touches | to the coder, in that module's own commit |
| `msgid` - a source string is wrong | to the coder |
| `platform` - core or an untouched module behaves so without the change | to the run summary, never to the coder |
| `oracle` - the expected value contradicts the SRS or the platform | to the summary as a question for the requirement's owner; its scenario leaves the roll-up |
| `environment` - the instance, the data or the browser | back to its gate, which re-runs the scenario on a corrected environment |

A scenario explained by several items stays a FAIL while one of them is bound for the coder.

## 2. Check before you send

Open the evidence of every item bound for the coder: the cited lines, the capture, the log. An
item whose evidence does not show what it claims goes back to R2 with what you saw. An item whose
`cause` is `hypothesis` and that rests on an acceptance FAIL goes to `odoo-debug` with the
tester's repro steps; the report replaces the item and its fix goes to the same coder. Any other
`hypothesis` travels labelled as one.

## 3. One resume of the coder

Send the fix list path and the item ids, never a fix direction. The coder answers per item: the
root it found, the change, the test that fails without the change, where else it looked for the
same cause - or `not a defect: <evidence>`, which goes back to R2.

## 4. Verify the fix, start nothing over

R2 rules each item `closed` or `open` on the fix diff and reads only the lines the fix wrote;
acceptance re-runs the failed scenarios and those the fix touched; the UI reviewer re-rates the
screens it touched.

## 5. When a fix does not hold

An item still `open`, or a new CRITICAL or HIGH in lines a fix wrote, is not patched again: the
next round carries a proven diagnosis - `odoo-debug` where a scenario reproduces it, otherwise the
reviewer relaunched one tier up with the chain of findings as evidence. At most three rounds per
change, counted over every review of it. After the third, or when the diagnosis names the design,
stop and hand the human the chain and its evidence.

A finding about how a screen looks is fixed like any other: the capture that showed it and the
coder's capture after the fix go in the summary, with no approval asked. A difference from the
mockup that the UI review marks as core's rendering is a note on the design, never an item.
