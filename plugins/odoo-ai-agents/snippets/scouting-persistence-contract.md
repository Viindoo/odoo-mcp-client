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

## Clause 3 - verbatim per-agent capture (Write-constrained dispatch)

Clause 2's "the PARENT skill writes this file after the scout returns" exists because a
Write-constrained agent type (`Explore`, or another anonymous read-only type) cannot save its own
file - that exception is about the TOOL, not the CONTENT. A parent that reworks a scout's return
into its own words recreates the exact failure this contract exists to close: a lossy digest
standing in for the actual finding is the caller's memory wearing a file. The parent's write MUST
be that scout's own returned text captured VERBATIM - no merging, no summarizing, no re-ordering,
and never folding two scouts' distinct findings into one line.

**One scout dispatched (the common case).** Its verbatim return is transcribed into `findings.md`
per Clause 2's schema - one distinct fact per line, exactly as the scout reported it. Truncate via
Clause 2's own 20-line cap if there are more facts than the cap allows; never compress two
distinct facts into a single line to stay under it.

**More than one scout dispatched in the same phase.** The FIRST scout's verbatim return goes to
`findings.md` (path and schema unchanged from Clause 2). EACH ADDITIONAL scout gets its OWN
sibling file in the same directory, `findings-<N>.md` (`<N>` = 2, 3, ... in dispatch order) -
never merged into `findings.md`, never summarized into a shared line. `findings.md` gains one
closing line naming every sibling that exists for this run: `siblings: [findings-2.md, ...]`
(empty list when only one scout ran) - a reader knows the full set without globbing. A sibling
file holds that ONE scout's verbatim return only, nothing else: no header, no line/character cap
(Clause 2's 20-line/200-char cap governs `findings.md` only - a sibling is deliberately uncapped,
existing precisely to hold what the compact schema cannot).

**Read-back.** The consuming phase reads `findings.md` first; when `siblings` is non-empty and a
compact line needs the fuller context a merged summary would have lost, it reads the named
sibling(s) too - it never guesses at what a merged line left out.

**Consumer registry (authoritative, SSOT for this clause's readers).** Every site that dispatches
a Write-constrained scout and relies on this clause registers its row here. A row is
`<file path relative to the plugin root> | <section anchor - the exact substring marking that
site's own section>`. Adding a new such site anywhere in the tree requires BOTH adding its row
below AND citing "clause 3" within that site's own section (the anchor's section) - a row with no
citation, or a citation with no row, is a guard-test failure, not a style nit.

| file | section anchor |
|---|---|
| `skills/odoo-intake/SKILL.md` | `Persist before you propose` |
| `skills/odoo-modules-upgrade/references/upg-phase-detail.md` | `### P1a - DAG build` |
| `skills/odoo-modules-upgrade/references/upg-phase-detail.md` | `### P1d - Transitive Symbol Survey` |

## Relation to the worklog

`${CLAUDE_PLUGIN_ROOT}/snippets/worklog-contract.md` records DECISIONS and why; this records OBSERVATIONS of current state - a finding that becomes a decision is logged in both, in its own vocabulary, and neither file restates the other.
