# A resumed review round

For `odoo-code-reviewer` when its brief carries `PRIOR_FINDINGS` or `ACCEPTANCE_EVIDENCE`.

## Verifying a fix

`PRIOR_FINDINGS` given: for each earlier finding, read the fix diff and decide `fixed` (with the
new line), `not fixed` (why) or `withdrawn` (the coder's evidence it was not a defect). New
findings outside the fix diff are written only when CRITICAL or HIGH; everything else goes to a
`debt` list. In `R1`, re-run only the checks of the earlier findings on the changed files.

## Classifying acceptance failures

`ACCEPTANCE_EVIDENCE` given (`R2`): for each FAIL, name the cause - `code` (the code contradicts the
SRS; the fix is a finding), `oracle` (the scenario contradicts the SRS; the human decides), `msgid`
(a source string is wrong), or `environment` (the instance, data or browser) - and merge the
`code` ones into the findings, deduplicated by symbol and line. Before naming `environment` for a
UI symptom, list every template patch the changed modules make on that component (`t-inherit`,
`inherit_id`) and exclude each by evidence; the classification carries that list.
