<!-- SSOT snippet. The boundary for RUNNING tests/instance work: who runs, when to keep it
     inline vs delegate, INSTANCE_HANDLE precedence, the NEEDS_NEXT escalation, and the
     output-volume rule that keeps the caller's context clean. Referenced (not copy-pasted) by
     odoo-qa-tester, odoo-acceptance, odoo-forward-port, odoo-coder, odoo-code-reviewer, and
     odoo-frontend-coder. Canonical NEEDS_NEXT example lives in odoo-test-writing Round 5.
     Edit here only; consumers point at ${CLAUDE_PLUGIN_ROOT}/snippets/test-execution-handoff.md. -->

# Test-Execution Handoff Contract (who runs the suite, and where the output goes)

Writing a test, running a test, and judging the result are three different jobs. Folding the run
into the writer's or the orchestrator's own context mixes the roles AND floods that context with
test logs and tracebacks. This contract keeps them separate and keeps heavy output out of the
caller.

## Three roles, three contexts

- **Author** - writes the test or the oracle (`odoo-test-writing`, `odoo-qa-planner`). Does NOT
  decide PASS from a run it controls.
- **Execute** - provisions/operates the live instance and runs the suite (`odoo-instance` skill ->
  `odoo-instance-ops` agent). Returns structured results, not raw firehose.
- **Adjudicate** - compares observed-vs-oracle and rules PASS/FAIL/UNVERIFIED (`odoo-qa-tester`,
  or the consuming reviewer/orchestrator). Anti-bias rules:
  `${CLAUDE_PLUGIN_ROOT}/snippets/acceptance-oracle-contract.md`.

## Keep inline vs delegate

Run a check inline ONLY when it is small, immediate, and its output is bounded:
- a single unit/`TransactionCase` method or a focused `Form()` assertion you need right now,
- a quick `set_active_version` reachability probe, a bounded lint of one file.

DELEGATE to `odoo-instance` (which dispatches `odoo-instance-ops`) when any of these hold:
- the full module suite or a cross-module/cluster run,
- a run needing a live HTTP server (tour / `HttpCase` / `url_open`, requires `--http-port`),
- demo=on integration runs, install/upgrade (`-i` / `-u`) of a cluster,
- output would be large (full test log, tracebacks, query-count dumps).

The writer/orchestrator MUST NOT allocate a DB + port and run a full suite inside its own context -
that is the executor's job and it pollutes the caller.

## INSTANCE_HANDLE precedence (provided handle always wins)

If the brief carries an `INSTANCE_HANDLE`, USE IT for every odoo-bin operation - do NOT allocate
your own db_name / port / addons_path (self-provisioning collides on port 8069 / DB name when
agents run concurrently). Only when NO handle was passed does the executor acquire its own isolated
ephemeral instance. Full contract: `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`.

## NEEDS_NEXT escalation (no instance to run against)

When a run is required but no live instance is reachable and none was handed in, do NOT fake a
green result and do NOT block outright. Emit a Continuation Contract
(`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`) with `status: NEEDS_NEXT` routing to
the `odoo-instance` skill - canonical shape in `odoo-test-writing` SKILL Round 5:

```
status: NEEDS_NEXT
next:
  - skill: odoo-instance
    reason: provision the live instance needed to run the suite / tours and adjudicate
    inputs: {operation: run-tests, series: "<series>", modules: [<test_set>]}
    confidence: 0.9
    risk_level: L2
```

Authoring (writing the test/oracle) proceeds regardless; only EXECUTION waits on the instance.
Fall back to `BLOCKED` only when provisioning itself is impossible.

## Invocation mode, log mode, and warnings-are-findings

When dispatching `odoo-instance` run-tests, the caller picks:
- `mode`: `fresh` (new DB - init + run the suite in one pass) or `reuse` (the DB already has the
  module - re-init data + re-run). Re-runs need `reuse`; on an already-installed module a `fresh`
  invocation is a no-op, so the suite silently does not re-run.
- `log_mode` (optional): `warn` | `info` | `debug` | `sql`.

A run's `warnings > 0` MUST be surfaced as findings alongside failures and errors - never swallowed.
WARNINGs are defects to fix, not noise. Flag-level detail for both params (the `-i`/`-u` mapping and
the log-flag table): `${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md`
(§ Core test invocation, § Log verbosity modes).

## Output-volume contract (return the verdict, not the firehose)

The executor and the adjudicator return a compact verdict plus a POINTER to evidence on disk - they
do NOT dump the full test log, traceback, or screenshot stream into the caller's context. Write the
detail to the run's artifact (e.g. `.odoo-ai/qa/<slug>-acceptance-report.md`, the instance log path)
and return: the verdict, per-scenario PASS/FAIL/UNVERIFIED counts, the top failure(s) with a one-line
repro, and the artifact path. The point of delegation is a clean caller context - inlining the log
defeats it.
