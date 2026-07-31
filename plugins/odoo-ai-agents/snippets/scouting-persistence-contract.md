<!-- SSOT snippet. Home for the scouting/recon persistence + read-back contract shared by every
     skill whose first phase SURVEYS before a later phase acts. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/scouting-persistence-contract.md. Tier classification of the
     paths named here is owned by ${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md - not
     restated here. -->

# Scouting persistence contract (SSOT)

A scouting phase (intake Phase R, forward-port P0, a review/doc scoper, a rebase intake) spends real
tokens discovering current state. Findings kept only in the orchestrator's context force a resumed
run to re-scout from zero and a sibling phase to re-derive what a peer already knew. This contract
makes the finding a FILE and makes the consumer READ it.

## Clause 1 - read-back discipline (every scouting artifact, wherever it lives)

Existing artifacts KEEP their current tier and filename - this clause adds no path change.

- **Write:** at the end of your scouting phase, before the plan/gate/next phase - return a POINTER plus counts to your caller, never an inline dump of the findings.
- **Read:** the consuming phase names the artifact by filename and re-reads it from disk before it dispatches - it does not rely on the scout's returned text still being in context.
- **Resume:** before dispatching a scout, glob for a matching artifact for THIS slug. Present -> read it and skip the dispatch. Absent -> dispatch. Never dispatch a scout twice per slug per run.
- **Staleness:** slug matches but the recorded target ref/branch does not -> STALE - re-dispatch and overwrite, recording `stale: <old-ref> -> <new-ref>` in the new file. This clause applies only to a consumer whose OWN artifact schema actually carries the ref it checks (e.g. Clause 2's `target_ref:` header, or `_scope.md`'s `base_ref:`) - a consumer with no such field (and no staleness clause of its own) is unaffected.

## Clause 2 - the path for a scouting phase that writes NO file today

Intake Phase R and forward-port P0 have no artifact at all. They write exactly one:

```
<ISOLATE_DIR>/recon/<slug>-<date>/findings.md
```

Resolve `<ISOLATE_DIR>` ONCE per `state-root-resolution.md`'s resolve-capture-substitute protocol and
substitute the captured absolute literal. The dispatched scout stays WRITE-FREE - the PARENT skill
writes this file after the scout returns.

**Header line (staleness anchor - written once, the FIRST line of the file, before any finding
line; NOT one of the capped finding lines below - same field role as `_scope.md`'s `base_ref:`,
`agents/odoo-review-scoper.md:200`):**

```
target_ref: <ref>
```

`<ref>` is the git ref the working tree was on when this file was written -
`git rev-parse --abbrev-ref HEAD`, or the short SHA (`git rev-parse --short HEAD`) when `HEAD` is
detached. This is the exact field Clause 1's staleness check reads. When a resume overwrites a
STALE file, the new file's header gains a second line immediately below `target_ref:`:
`stale: <old-ref> -> <new-ref>`.

One line per finding, exactly these four fields in order:

```
- <area> | <finding> | <citation: file:line | OSM <tool>(<args>) | none> | resolved:yes|no
```

**Cap: at most 20 finding lines, at most 200 characters each** (the `target_ref:`/`stale:` header
lines above are NOT finding lines and do not count against this cap - two short header lines add
well under 100 bytes to a file already bounded at ~4 KB/run, so this does not push the file over the
declared cap). Over the cap, keep the 20 most decision-relevant and append: `- (truncated) | <n>
findings dropped at the 20-line cap | none | resolved:no`.

**Retention:** keep it, never delete - bounded (~4 KB/run) and the resume rule above reads it. One dir per `<slug>-<date>`; a repeated slug on the same date overwrites rather than accumulates.

## Relation to the worklog

`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md` records DECISIONS and why; this records OBSERVATIONS of current state - a finding that becomes a decision is logged in both, in its own vocabulary, and neither file restates the other.
