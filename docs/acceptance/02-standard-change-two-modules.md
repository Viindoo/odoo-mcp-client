# Scenario 2 - a Standard change touching two modules, one adds a dependency

**Setup.** A change whose SRS rule says "no SRS": an existing feature's rule changes inside two
modules, and one of them adds a module to its `depends`.

**Run.** `/odoo-intake "<the change>"` - the main agent launches `odoo-coder` directly.

**Measure:**
- the coder runs at `haiku` (the six-item checklist holds);
- the stand-alone database installs only the node's modules plus their `depends` closure, the
  second database adds the dependents;
- the test the coder wrote is red before the code and green after (two runs in the worklog);
- no review finding about the changed `depends` (the module is in `W`, read from disk, never
  from the index);
- the worktree path matches `$ODOO_AI_HOME/projects/<repo-key>/worktrees/<name>/src`.

**Pass when** all five hold and R1 then R2 return `APPROVE` within one round.
