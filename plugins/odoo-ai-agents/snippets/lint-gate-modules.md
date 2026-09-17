<!-- SSOT snippet. The single home for WHICH modules make up the backend lint-class gate, how to
     select them for a series, and the stale-index false-green trap. Consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/lint-gate-modules.md - never restate the module set elsewhere.
     The series boundary itself lives in odoo-version-pivots.md; do not copy it here. -->

# Backend lint-class gate - module selection

The backend code-quality gate is Odoo's own lint test module plus, on a Viindoo profile, Viindoo's
lint module. This snippet decides WHICH modules the gate is made of. WHETHER the gate runs on a
given dispatch is a separate decision owned by `GATE_ROLE`
(`${CLAUDE_PLUGIN_ROOT}/agents/odoo-instance-ops.md` § Lint modules).

## Candidate set

`test_lint`, `test_pylint`, `test_viin_pylint`.

`test_lint` is Odoo core and keeps its name across every indexed series. The two Viindoo names are
ONE gate that changed name at a series boundary - that boundary, and which name belongs to which
series, are in `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § Backend lint-class gate.

## Selection - run every step, in order

1. Read the pivots section above and resolve the ONE Viindoo lint module name for the target series.
   Carry only that name forward; the other name is not a fallback.
2. Probe `check_module_exists(name='<module>', odoo_version='<series>', profile_name='<pinned profile>')`
   for `test_lint` and for that ONE Viindoo name. Pass `profile_name=` explicitly on every call -
   never rely on an ambient profile pin.
3. For every module that comes back Indexed = Yes, union it into BOTH the `-i`/`-u` install list AND
   `--test-tags` (`/test_lint`, `/<resolved Viindoo name>`), from that SAME probe. Never tag a module
   you did not also install.

## A probe is not proof - the index can be stale (HARD RULE)

`check_module_exists` answers from the revision it indexed, so it can still report Indexed = Yes for
a module name the series has already renamed away. That name installs nothing, its tag matches
nothing, and the run reports a clean pass anyway - a FALSE GREEN on the one gate whose job is to
catch what review missed.

On the dispatch that runs this gate:

- NEVER union both Viindoo names because both probed Indexed = Yes. Step 1 decides the name; the
  probe only confirms the pinned profile carries it. Two lint modules from the same distribution in
  one build is a defect, not belt-and-braces.
- After the run, confirm from the build log that every tagged lint module actually INSTALLED and its
  tests LOADED. A module that was tagged but whose tests never loaded makes the gate
  `tests-inconclusive`, never a pass - report it as a finding and name the module.
