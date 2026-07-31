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
- **Staleness:** slug matches but the recorded target ref/branch does not -> STALE - re-dispatch and overwrite, recording `stale: <old-ref> -> <new-ref>` in the new file.

## Clause 2 - the path for a scouting phase that writes NO file today

Intake Phase R and forward-port P0 have no artifact at all. They write exactly one:

```
<ISOLATE_DIR>/recon/<slug>-<date>/findings.md
```

Resolve `<ISOLATE_DIR>` ONCE per `state-root-resolution.md`'s resolve-capture-substitute protocol and
substitute the captured absolute literal. The dispatched scout stays WRITE-FREE - the PARENT skill
writes this file after the scout returns.

One line per finding, exactly these four fields in order:

```
- <area> | <finding> | <citation: file:line | OSM <tool>(<args>) | none> | resolved:yes|no
```

**Cap: at most 20 finding lines, at most 200 characters each.** Over the cap, keep the 20 most
decision-relevant and append: `- (truncated) | <n> findings dropped at the 20-line cap | none | resolved:no`.

**Retention:** keep it, never delete - bounded (~4 KB/run) and the resume rule above reads it. One dir per `<slug>-<date>`; a repeated slug on the same date overwrites rather than accumulates.

## Relation to the worklog

`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md` records DECISIONS and why; this records OBSERVATIONS of current state - a finding that becomes a decision is logged in both, in its own vocabulary, and neither file restates the other.
