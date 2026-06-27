# Artifact voice - state the truth, not the journey (SSOT)

An artifact outlives the process that produced it. A reader months later needs to
know what the system IS and what the deliverable SAYS - not what was tried, in what
order, by whom, or which ticket tracked it. Process narration goes stale the moment
it ships and forces every future reader to subtract history from fact.

## The contract

Every ARTIFACT this plugin's skills and agents produce - reports, proposals,
design docs, marketing copy, code, docstrings, checklists, generated skills -
is written in present-tense, current-state voice:

1. **No process narration.** Do not write "we first tried X, then switched to
   Y", "after investigating, ...", "this was added because the review found
   ...". State the result and, where useful, the reason that still holds.
2. **No dates-as-provenance.** "verified <date>", "as of <date>", "(updated
   <date>)" do not belong in a deliverable body - the fact either holds or the
   artifact needs fixing. (Dates that ARE data - a deadline, a report period,
   an example record - are fine.)
3. **No tracker references.** Issue numbers, PR numbers, failure-log names,
   and review-finding IDs live in the tracker and the commit message, not in
   the artifact. If the reason behind a rule matters, state the reason itself.
4. **No before/after narration about the system.** "no longer", "previously",
   "used to", "the new behavior" describe a diff, not a state. Write what the
   system does now. (Facts about EXTERNAL version history - e.g. an Odoo API
   removed in a given version - are domain knowledge, not narration: keep them.)

## What is exempt

Artifacts whose PURPOSE is to record history keep it: changelogs, commit
messages, migration notes, audit trails, session reports, and the evidence
sections of debug/review reports (a root-cause proof must show the
reproduction). Chat conversation with the user may narrate freely - this
contract governs the files and copy that ship.

Self-check before emitting an artifact: "if a stranger reads only this file in
six months, does every sentence still earn its place?" Sentences about the
journey fail that test; sentences about the destination pass.
