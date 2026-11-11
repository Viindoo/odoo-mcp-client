# Artifact voice - state the truth, not the journey

An artifact outlives the process that produced it. Its reader needs what the system is and what the
deliverable says, not what was tried, in what order, by whom or under which ticket. This binds
every artifact a skill or agent of this plugin writes: designs, requirement specifications, plans,
acceptance oracles, recon and review reports, documentation, proposals, marketing copy, pull
request bodies.

1. **No process narration.** Not "we first tried X, then switched to Y", "after investigating",
   "added because the review found". State the result and, where it helps, the reason that still
   holds.
2. **No dates as provenance.** "verified <date>", "as of <date>", "(updated <date>)" do not belong
   in a deliverable: the fact holds or the artifact needs fixing. A date that is data (a deadline,
   a report period, an example record) stays.
3. **No tracker references.** Issue, pull request, failure-log and review-finding ids live in the
   tracker and the commit message. When the reason behind a rule matters, state the reason.
4. **No before and after.** "no longer", "previously", "used to", "the new behaviour" describe a
   diff, not a state. A fact of external version history (an Odoo API removed in a given series)
   is domain knowledge and stays.
5. **Edit in place.** A text that changes is rewritten coherently to its new state. No appended
   "update", "addendum", "exception" or "decisions taken at the gate" section, in a design as in a
   pull request body.

A design keeps the reason for a decision next to the decision, in the present tense; it keeps no
list of the alternatives considered.

Comments, docstrings and user-visible strings in source are governed by
`${CLAUDE_PLUGIN_ROOT}/snippets/code-comment-contract.md`.

**Exempt:** artifacts whose purpose is the record - changelogs, commit messages, worklogs, audit
trails, session reports, and the evidence section of a debug or review report (a root-cause proof
shows its reproduction). Conversation with the user may narrate.
