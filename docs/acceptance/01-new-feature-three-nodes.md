# Scenario 1 - a new feature across three nodes, two languages

**Setup.** A declared instance whose catalog row lists two languages; a request for a feature the
SRS rule classifies as non-trivial (it spans three modules).

**Run.** `/odoo-intake "<the feature>"` and follow every gate: approve the SRS, the design, the
plan, the merge.

**Measure** (from `<ISOLATE_DIR>/worklog/<run>/` and the run file):
- launches per tier: expected about architect 1 (opus), recon 1 (haiku), planner 1 (sonnet),
  coder 3, reviewer R1 1 (haiku) + R2 1 (sonnet) + R3 only when the taxonomy or the recon
  thresholds call for it, tester 1 (haiku), translator 2 (sonnet), doc-writer 3 (sonnet),
  monitor 1 (haiku);
- wall time per stage;
- review rounds (at most 3) and the final verdict;
- the acceptance report: PASS / FAIL / UNVERIFIED per database;
- `doc/index.rst` per language, read by a person holding each audience role: they find the
  menu, the button and the outcome the guide describes without help.

**Pass when** the PR opens with every node `DONE`, the counts are within the expectation, and
the reader test holds for every role.
