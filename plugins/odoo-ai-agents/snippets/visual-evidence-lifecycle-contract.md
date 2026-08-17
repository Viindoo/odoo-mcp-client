<!-- SSOT snippet. Home for (1) the collision-proof slug-derivation rule shared by every
     skill that mints a visual/-rooted per-run evidence path (the four sibling
     visual/*/<slug>/ directories, plus odoo-demo-recording's visual/videos/ filename), and
     (2) the orphan-sweep GC rule for EVERY run-scoped Tier-2 ISOLATE subpath in the plugin
     (Clause 3 generalizes Clause 2 beyond visual/ to the full ISOLATE surface). Edit here
     only; consumers point at ${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md.
     Tier and bucket classification of these paths is owned by
     ${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md - not restated here. -->

# Run-scoped visual evidence: slug + retention (SSOT)

Four skills each mint a per-run `<slug>/` evidence directory under `visual/`:
`odoo-visual-regression` (`visual/current/<slug>/`), `odoo-acceptance` via `odoo-qa-tester`
(`visual/qa/<slug>/<module>/`), `odoo-debug` via `odoo-ui-debugger` (`visual/debug/<slug>/`),
and `odoo-ui-review` via `odoo-ui-reviewer` (`visual/screenshots/<slug>/`). Both the slug
ITSELF and the directory's LIFETIME are the same defect class stated twice - a bare intent
slug collides under concurrency, and an evidence directory nobody ever deletes leaks disk
forever - so this file states both rules once for all four. Clause 3 below generalizes the
retention half (only) of this rule to every OTHER run-scoped ISOLATE subpath in the plugin -
the same leak, one directory per run, is not unique to `visual/`.

A fifth skill, `odoo-demo-recording`, mints a per-run FILENAME (not a directory) under the same
`visual/` root - `visual/videos/<feature>-<slug-suffix>.{mp4,gif}` - and is exposed to the
identical collision half of this defect class (two concurrent runs on a similarly-named feature
overwriting each other's clip) even though its retention half already has its own row in Clause 3
§3.1 (single terminal file, 30-day bound, no directory to sweep). Clause 1 below therefore governs
both shapes - directory and filename - under one mechanism; do not derive a second one for the
filename case.

## Clause 1 - collision-proof slug derivation

Mint the slug ONCE, at the start of the run (before any path that embeds it is touched):

```
<intent-slug>-<YYYYMMDD>-<4 random chars>
```

**Generation mechanism (SSOT - the FORMAT above named the shape; this is the ACTION that
produces it).** Run, via the Bash tool, and take the result verbatim as `<4 random chars>`:

```bash
printf '%02x%02x' $((RANDOM % 256)) $((RANDOM % 256))
```

This is a bash-builtin-only, zero-dependency, POSIX-portable one-liner (`$RANDOM` is a bash
builtin present in every environment this plugin already assumes - no `/dev/urandom`,
`uuid`, `python3`, or external binary required) that yields exactly 4 lowercase hex
characters (`0000`-`ffff`, e.g. `a1b2`, `9f3d`). Two separate `$((RANDOM % 256))` draws are used (not one `$((RANDOM % 65536))`
call) because `$RANDOM` itself is only a 15-bit generator (range 0-32767) - drawing two
independent bytes is what actually reaches the full 4-hex-digit space the format promises,
not merely a value that happens to print in 4 hex digits.

**Fit for purpose, not a security token.** This is a same-day, same-intent, concurrent-run
DISAMBIGUATOR, never a security/secrecy boundary - nothing in this plugin treats the slug as
a capability token (contrast `run_id`, which `assert-droppable`/`release` treat as
"semi-discoverable", never as a secret either). `$RANDOM`'s pseudo-randomness (seeded per bash
process) is more than adequate for this: the failure mode being avoided is two concurrent runs
on the identical intent the same day picking the IDENTICAL 4-char suffix, not an adversary
guessing it. Do not upgrade this to a cryptographic source (`openssl rand`, `/dev/urandom`) -
that would add a dependency this mechanism deliberately has none of, for a property (secrecy)
this slug does not need.

An agent context invoking this MUST actually run the one-liner above via the Bash tool and use
its printed output - never sample "4 random-looking characters" from its own reasoning instead
of a true tool call; two independent agent contexts reasoning about the identical intent text
are not provably independent samples the way this command's output is.

The IDENTICAL suffix mechanism `${CLAUDE_PLUGIN_ROOT}/skills/odoo-intake/references/phase-p-run-dag.md:43`
uses for its `run-<id>.json` id ("so concurrent runs never collide") is the ONE above - do not
invent a second algorithm, and do not restate this one; point back at this clause instead. Use
the `SLUG:` value from your dispatch brief when a caller supplies one; derive fresh only on a
standalone invocation with no caller-supplied slug. Mint it exactly once per run and reuse that
SAME value for every artifact path the run touches - never improvise a fresh one per
screen/module/step, never re-mint the random suffix mid-run, never leave the literal `<slug>`
token itself in a path.

**Worked example - two concurrent same-intent runs.** Intent "compare before/after the v17
upgrade" fired twice concurrently:

`compare-v17-upgrade-20260731-a1b2` and `compare-v17-upgrade-20260731-9f3d`

Same intent-slug and date, different random suffix - the two runs write to different
directories and neither overwrites the other's evidence.

**Why the random suffix, not just the date.** `<ISOLATE_DIR>` is worktree-keyed, not
run-keyed (`state-root-resolution.md`), and any of these four skills may run standalone
(exempt from wider run/worktree provisioning) - date alone still collides when two callers
fire the identical intent the same day. The 4-character random suffix is the disambiguator.

**Fifth consumer - a filename, not a directory.** `odoo-demo-recording` applies this SAME rule
to its video artifact name instead of a directory: `<feature>-<YYYYMMDD>-<4 random chars>.{mp4,gif}`
under `visual/videos/` (`<feature>` plays the role of `<intent-slug>`; full wiring:
`skills/odoo-demo-recording/SKILL.md` § Round 4 and § Narrated evidence mode). Mint it once per
run, before Round 4's orphan sweep, and reuse the SAME value for both takes of a narrated
before/after pair (the `-before`/`-after` suffix is appended on top, never a second random mint).
This closes the exact gap a bare `<feature>-<timestamp>` resolving to a date-only string would
leave: two same-day recordings of a similarly-named feature would otherwise silently overwrite
each other's clip - the identical failure mode the four directory-based siblings above avoid by
the same mechanism. Any FUTURE skill that mints a new `visual/`-rooted per-run path - directory or
filename - follows this same Clause 1 rule; do not invent a per-skill variant.

## Clause 2 - orphan-sweep retention (GC)

**Eligible:** ONLY the four `visual/*/<slug>/` ISOLATE subpaths this file names (bucket 2,
run-scoped evidence, per `state-root-resolution.md` § Where a captured artifact goes). NEVER
a SHARE reusable cache (`visual/baselines/`, `visual/doc/`) - its whole value IS surviving
across runs, so sweeping it on a TTL would destroy the thing it exists to provide. NEVER a
committed module deliverable (bucket 3) - it is reached only by an explicit copy into the
module tree and thereafter lives under git, entirely outside this sweep's reach.

**Bound.** `visual/current/<slug>/` already self-deletes at its own run's terminal status
(`odoo-visual-regression/SKILL.md` § Retention); its TTL backstop stays the existing 24h
(mtime), for the crash-only case. The other three (`qa/`, `debug/`, `screenshots/`) are
deliberately RETAINED past their own run's terminal status - they are the cited evidence
behind a PASS/FAIL verdict, a diagnosed root cause, or a review finding - so a 24h sweep
would delete evidence a human or a later phase still needs. Their bound is **30 days
(43200 minutes, mtime)**: long enough that the evidence outlives the run that produced it
and any immediate follow-up, short enough that disk growth stays bounded to roughly one
month of runs rather than forever.

**Who sweeps, when.** The skill that owns each subpath sweeps its OWN sibling directories,
unconditionally, at its own Phase/Round 0 - BEFORE minting its own run's `<slug>` (Clause 1)
- exactly the pattern `odoo-visual-regression`'s Round 0 already applies to `visual/current/`:

```
find <ISOLATE_DIR>/visual/<subdir>/ -mindepth 1 -maxdepth 1 -type d -mmin +<bound-in-minutes> -exec rm -rf {} +
```

`odoo-acceptance` sweeps `visual/qa/` (mmin +43200), `odoo-debug` sweeps `visual/debug/`
(mmin +43200), `odoo-ui-review` sweeps `visual/screenshots/` (mmin +43200) - each at its own
Phase/Round 0, each scoped to only its OWN subdirectory, never a sibling it does not own.
Enforcer: whoever executes that skill next, unconditionally, every run - not a separate
cleanup agent or cron; no hook tracks a filesystem directory the way the allocator ledger
tracks an instance lease.

**Concurrency protection (the dangerous failure mode).** The sweep can NEVER delete a
concurrent run's live directory, for two independent reasons, either one sufficient alone:
(1) `-mmin +<bound>` matches only a directory UNTOUCHED for the full bound - a live run keeps
writing into its own `<slug>/` dir throughout its execution, continuously refreshing its
mtime, so it never ages past the threshold while still running; (2) the sweep runs BEFORE
this run mints its OWN new slug (Clause 1), so it can never match the directory THIS run is
about to create. A directory only matches the sweep once its owning run reached a terminal
status (and stopped writing) and then sat untouched for the FULL bound - by which point every
terminal-status path (DONE/BLOCKED/NEEDS_CONTEXT/NEEDS_NEXT) has already had 30 days to have
its evidence consumed.

## Clause 3 - generalized ISOLATE-tier orphan sweep (every OTHER run-scoped subpath)

Clause 2's leak is not unique to `visual/`. Every Tier-2 ISOLATE subpath in
`state-root-resolution.md`'s ISOLATE table is, BY DEFINITION of that tier ("run/session-scoped
active state" - see that file's § The rule), a candidate for the identical leak: nothing has
ever deleted any of them. This clause enumerates the FULL ISOLATE table (exhaustive per that
file's own claim) and classifies each row once, so a later reader never has to re-derive it.
Tier-1 subpaths (`logs/`, `conf/`) are OUT OF SCOPE here - see § 3.7.

### 3.1 - Eligible (bucket 2, run-scoped evidence/working-state - swept)

| Subpath | Owner | Bound | Why this bound |
|---|---|---|---|
| `worklog/<run-or-slug>/` | every multi-agent run (via `worklog-contract.md`) | 30d | decision log stays useful after the run for the next resume/audit; no self-cleanup step exists |
| `integration/<slug>/` | `run-harness` (integration) | 24h | Self-deletes at its own post-merge cleanup (`run-integration.md` § Cleanup Checklist). TTL crash-backstop wired at `run-harness/SKILL.md` § Run start + `run-integration.md` § Stale integration-dir sweep - fail-closed, run-status-correlated (never a bare mtime check; see § 3.6 for why the naive Clause-2 recipe was unsafe here). |
| `git-rebase/<slug>/` | `odoo-git-rebase` | 30d | checkpoint/commit-dump working state; retained as evidence of what the rebase did, no self-cleanup step |
| `forward-port/<slug>/` | `odoo-forward-port` | 30d | same reasoning as `git-rebase/<slug>/` |
| `modules-upgrade/<slug>/` (+ `checkpoint.json`) | `odoo-modules-upgrade` | 30d | same reasoning as `git-rebase/<slug>/` |
| `coding/<slug>-<date>/` (`plan.md`) | `odoo-coding` | 30d | a later review/fix/resume step reads it to avoid recomputing the graph; no self-cleanup step |
| `reviews/<slug>-<date>/` | `odoo-code-review` | 30d | tied to one diff/branch/PR; retained as the review's own evidence |
| `pr-monitoring/<id>.md` | `odoo-pr-monitoring` | 30d | rewritten on every poll tick while monitoring is active - only goes stale once monitoring has genuinely concluded (merged/abandoned) |
| `followups/<slug>.md` | `odoo-draft-followup` command | 30d | terminal deliverable - the run concludes the instant this file is written, so there is no "still alive" window to protect against. Wired at `commands/odoo-draft-followup.md` § Phase 0, step 0. |
| `visual/videos/<feature>-<YYYYMMDD>-<4 random chars>.{mp4,gif}` (a FILE - `state-root-resolution.md`'s ISOLATE-table trailing `/` on this row is loose notation, not a real directory) | `odoo-demo-recording` | 30d | terminal deliverable, same class as `followups/<slug>.md`; the filename itself is collision-proofed per Clause 1's fifth-consumer rule above, not merely a bare `<timestamp>` |
| `visual/<run_id>/<module>_staging/` | `odoo-doc-illustration` | 24h | ALREADY self-deletes at its own end-of-run staging cleanup (`odoo-doc-illustration/SKILL.md` § End-of-run staging cleanup) - the TTL is a crash-only backstop, same class as `integration/<slug>/` and `visual/current/<slug>/` |
| `i18n/<slug>-<date>/` | `odoo-i18n` | 30d | the i18n recipe already mandates a fresh export on every invocation and forbids reusing a prior run's artifacts (`i18n-mandate-contract.md`) - anything past the very next run is already-superseded, but 30d still gives grace for a delayed review of the translation report |
| the 13 workflow `output_dir` trees (`bids/`, `content/`, `debug/`, `discovery/`, `implement/`, `packaging/`, `positioning/`, `qa/`, `research/`, `sales/`, `support/`, `upgrade-plans/`, `video/`) | `workflow-chaining` (the single runner for all 13) | 30d | same retained-evidence reasoning; swept ONCE generically at Phase 0 for whichever `output_dir` the active workflow declares, rather than thirteen separate call sites |
| `visual/current/<slug>/`, `visual/qa/<slug>/<module>/`, `visual/debug/<slug>/`, `visual/screenshots/<slug>/` | see Clause 2 | 24h / 30d | already covered above - listed here only for completeness of the full ISOLATE enumeration |

No third bound was needed: every eligible row is either (a) already self-deleted at its own
terminal status, in which case it reuses the 24h crash-backstop, or (b) deliberately retained
with no self-cleanup step, in which case it reuses the 30-day bound. A row needing neither
pattern did not arise.

**Sweeping a shared parent directory - exclude siblings by name.** `visual/<run_id>/<module>_staging/`'s
own 24h crash-backstop cannot blindly sweep every immediate child of `visual/` the way the other
rows sweep their OWN dedicated subdir - `visual/` is the shared parent of `baselines/`, `doc/`
(SHARE) AND `current/`, `qa/`, `debug/`, `screenshots/`, `videos/` (four other skills' OWN ISOLATE
trees), none of which are `<run_id>/` dirs. A naive `find <ISOLATE_DIR>/visual/ -mindepth 1
-maxdepth 1 -type d -mmin +1440 -exec rm -rf {} +` would delete those ENTIRE sibling trees the
moment their own top-level directory goes 24h without a NEW child being created inside it - far
worse than the leak this contract exists to close. The sweep MUST exclude all seven known
siblings by name (`! -name baselines ! -name doc ! -name current ! -name qa ! -name debug ! -name
screenshots ! -name videos`) so only an actual `<run_id>/` leftover matches
(`odoo-doc-illustration/SKILL.md` § the exact command). Any future skill adding an EIGHTH named
child directly under `visual/` must add itself to this exclusion list, or `odoo-doc-illustration`'s
crash-backstop would delete that new sibling's tree the same way.

### 3.2 - Not eligible / never eligible / not applicable (excluded, with reasons)

| Subpath | Classification | Reason excluded |
|---|---|---|
| `recon/<slug>-<date>/` (`findings.md`) | Retention-protected, not swept | `scouting-persistence-contract.md` Clause 1 already states "Retention: keep it, never delete" and bounds the file to ~4 KB/run by its own line/char cap - a competing, already-tested SSOT governs this path; sweeping it here would silently contradict that contract instead of reconciling with it |
| `run-<id>.json` | Excluded - mtime is not a reliable liveness signal here | see § 3.3 below |
| `brainstorm/state.json` | Not applicable - no leak | a SINGLE overwritten file with no `<slug>` in its name (unlike every other row in this table) - it does not accumulate one directory per run, so there is nothing to sweep |
| bucket-1 reusable caches (`visual/baselines/`, `visual/doc/`, `designs/`, `plans/`, `gap-analysis/`, `survey/<slug>-<date>/`, `brl/<job-id>/`, `documentation/...`, `brand-tokens.json`, `mockups/`, `glossary.yml`, `cost-config.json`) | NEVER eligible - SHARE tier | see § 3.4 below; not part of the ISOLATE table at all |
| a committed module deliverable (bucket 3) | NEVER eligible | reached only by an explicit copy into the module tree and thereafter lives under git - never resides under `.odoo-ai/` at all, so it is structurally outside this sweep's reach; no ISOLATE row is actually a bucket-3 item (confirmed by inspection - every ISOLATE row is either an agent-authored artifact or a staging area that PRECEDES a bucket-3 copy, never the deliverable itself) |

Every ISOLATE-table row not listed in § 3.2 is covered by § 3.1 - the enumeration is exhaustive
against `state-root-resolution.md`'s own exhaustive ISOLATE table.

### 3.3 - `run-<id>.json`: the write-once-while-still-alive failure mode

`run-<id>.json` is rewritten after every COMPLETED phase (`workflow-chaining` § Resume logic /
`run-harness` §8.3) - so far, the same mtime argument as every other row above would apply.
But a run legitimately PAUSES at a gate ("approve / refine / cancel", an L2 human-confirm, a
`/schedule` cron waiting on an external event) for an UNBOUNDED period while still alive and
resumable - nothing touches the file during that pause, so its mtime goes stale while the run
is NOT abandoned, only slow. Sweeping this file on ANY TTL risks deleting a legitimately-paused,
still-resumable run's ENTIRE blackboard - exactly the "GC worse than the leak" failure mode this
contract exists to prevent, and for the ONE file the workflow resume promise depends on most.
**Decision: `run-<id>.json` is EXCLUDED from this generalized sweep.** A correct fix needs a
non-mtime signal - e.g. only sweeping a `run-<id>.json` whose OWN recorded status is already a
terminal one (DONE/BLOCKED/NEEDS_CONTEXT), never one still mid-flight regardless of mtime - which
this pass does not implement. Recorded here as a known gap, not silently dropped.

### 3.4 - SHARE tier: closed - no disk-TTL sweep is coming, ever, by design

**Decision: SHARE is OUT OF SCOPE for this GC rule, by design - and that decision is now FINAL,
not merely deferred.** No SHARE row gets a TTL sweep from this contract, and no future revision
of this contract will add one: a generalized disk-age sweep is the WRONG tool for SHARE by
construction (it cannot distinguish "stale content, safe to refresh" from "still the only known
good copy, do not touch"), not merely a tool this pass happened not to build. Concretely, each
SHARE cache's OWN consumer already carries (or should carry) its own staleness/invalidation
check at the point it READS the cache - the same shape `scouting-persistence-contract.md`'s
`target_ref:` staleness clause already applies to `recon/`, or "pick the most recently modified
`designs/*.md`" - never a background sweep that runs whether or not anyone is about to read the
cache. If growth on disk (not staleness of content) becomes a real operational problem for a
SPECIFIC SHARE cache, the fix is a size- or count-based cap owned by that cache's OWN consumer
contract (e.g. "keep the 20 most recent `survey/<slug>-<date>/` trees, prune the rest"), never a
retrofit of this contract's mtime-TTL mechanism - the two are different tools for different
problems and must not be conflated. SHARE growth is bounded not by disk age but, when a
specific cache needs a bound, by that cache's own size/count cap.

### 3.5 - Where the sweep for each § 3.1 row lives

Same pattern as Clause 2, generalized: the owning skill sweeps its OWN subpath, unconditionally,
at its own Phase/Round 0 - BEFORE minting its own run's slug (or, for `workflow-chaining`,
before resolving/using the active workflow's `output_dir` slug) - citing this file rather than
restating the command. Two rows are wired ONCE at a shared chokepoint that already fans out to
many consumers, instead of once per consumer: `worklog/<run-or-slug>/` at `worklog-contract.md`
§ Where it lives (every worklog writer follows that contract, so one edit covers all of them),
and the 13 workflow `output_dir` trees at `workflow-chaining/SKILL.md` Phase 0 (the single
runner for all 13 workflows). Every other § 3.1 row is wired at its own owning skill.

### 3.6 - `integration/<slug>/` and `followups/<slug>.md`: the criterion design (both now wired)

A plugin-wide grep for the literal sweep-command shape (`mmin +`) against every row's named
owner file once found 15 of 17 present and exactly 2 absent - this table must never claim coverage
reality does not have (a row claiming a sweep that does not exist is worse than an honestly
documented gap). Both offending rows (`integration/<slug>/`, `followups/<slug>.md`) are now wired at
their owner files (§ 3.1 above states exactly where); this subsection keeps the criterion design
and its reasoning as reference material, so a later reader does not have to re-derive WHY the
`integration/<slug>/` recipe looks the way it does.

**`followups/<slug>.md` (owner: `commands/odoo-draft-followup.md`).** The simple case - a
terminal, single-file deliverable, same shape as `pr-monitoring/<id>.md`'s file-typed sweep
(§ 3.1, `-type f -name '*.md'`, not `-type d`):

```
find <ISOLATE_DIR>/followups/ -maxdepth 1 -type f -name '*.md' -mmin +43200 -exec rm -rf {} +
```

No concurrency hazard here: unlike `integration/<slug>/` below, a followup file is written ONCE and
never reopened by its own run (§ 3.1's own "no still-alive window to protect against"), so the
plain mtime sweep `pr-monitoring/` already uses is directly correct with no correlation check
needed. Wired at that command's Phase 0, step 0.

**`integration/<slug>/` (owner: `skills/run-harness/references/run-integration.md` /
`skills/run-harness/SKILL.md`) - a bare mtime sweep is UNSAFE here; do not copy Clause 2's generic
recipe verbatim.** Applying `find ... -mmin +1440 -type d -exec rm -rf {} +` as-is would reopen the
exact danger `run-<id>.json` is excluded from this sweep for (§ 3.3): `run-harness` can pause at an
L2 human-confirm gate for an UNBOUNDED period mid-run (`run-harness/SKILL.md` § Gate-tier
resolution - "ALWAYS human - emit gate, end turn, resume after approve/skip/cancel"), during which
`integration/<slug>/plan.md` sits untouched - its mtime goes stale while the run is PAUSED, not abandoned.

**The criterion (mtime alone is never sufficient; a candidate must ALSO be positively correlated
to a TERMINAL run status before it may be deleted) - read the status with `jq`, never `grep`.**
`run-<id>.json`'s own schema (`docs/reference/workflow-harness.md` §8.3) nests a SECOND,
differently-scoped `"status"` key inside EVERY entry of its `nodes[]` array (a per-node progress
flag: `PENDING`/`READY`/`RUNNING`/`DONE`/...) alongside the run's own top-level `"status"`
(`NEEDS_NEXT`/`DONE`/`BLOCKED`/`NEEDS_CONTEXT`) - an unanchored text match against either key name
cannot tell them apart. A raw `grep -q '"status"[[:space:]]*:[[:space:]]*"(DONE|BLOCKED|
NEEDS_CONTEXT)"'` against the whole file therefore matches on the ROUTINE, EARLY, common case of
the run's FIRST node reaching `"DONE"` - while the run itself is still very much alive and
`NEEDS_NEXT` - and would reap a live run's directory out from under it: the exact "GC worse than
the leak" failure this contract exists to prevent, and not a rare edge case (an early node
finishing is the NORMAL shape of an active run, not an anomaly). `jq -r '.status // empty'` reads
ONLY the JSON root's `status` field:

```
if command -v jq >/dev/null 2>&1; then
  find <ISOLATE_DIR>/integration/ -mindepth 1 -maxdepth 1 -type d -mmin +1440 -print0 |
  while IFS= read -r -d '' d; do
    slug="$(basename "$d")"
    run_file="<ISOLATE_DIR>/run-${slug}.json"     # integration/<slug>/ and run-<id>.json share ONE id
                                                    # (state-root-resolution.md: "per active run")
    status="$(jq -r '.status // empty' "$run_file" 2>/dev/null || true)"
    case "$status" in
      DONE|BLOCKED|NEEDS_CONTEXT) rm -rf "$d" ;;   # the correlating RUN's own top-level status
                                                     # positively proved terminal - safe to reap
      *) : ;;   # absent run_file, unreadable/malformed JSON, empty, or NEEDS_NEXT (still
                # mid-flight, possibly paused at an L2 gate right now) - skip, never delete
    esac
  done
fi
# jq unavailable -> skip the ENTIRE sweep this run rather than fall back to a raw-text match -
# an unprovable status is the SAME "do not delete" outcome as an absent/unreadable run file,
# extended to "the tool needed to read it correctly is itself absent".
```

Fail-closed on every axis, all collapsing to "skip, never delete": no correlating `run-<id>.json`
at all, the file exists but is not valid JSON, `.status` is absent/empty, `.status` is
`NEEDS_NEXT` (mid-flight, possibly mid-pause), or `jq` itself is unavailable. Only a POSITIVELY
confirmed terminal top-level status on the run whose id matches the candidate directory's own
name authorizes deletion - mirroring `reap-orphans`' own age-unknown-means-not-reaped convention
(`scripts/lib/allocator.py` `_reap_candidates`) and the resolve-or-refuse discipline this contract
already applies to `run-<id>.json` itself (§ 3.3). This is deliberately NOT a bare one-liner like
the other 14 rows - it trades that uniformity for the one property that actually matters here: it
can never delete a live paused run's evidence. Wired at `run-harness/SKILL.md` § Run start
(the first action there, before this run creates or writes anything under
its OWN `integration/<slug>/` for the first time) and detailed at `run-integration.md` § Stale integration-dir
sweep.

### 3.7 - Tier-1 `logs/` and `conf/`: swept elsewhere, deliberately outside this clause

`logs/` and `conf/` are Tier-1 FLAT (`state-root-resolution.md`'s Tier-1 allowlist), not Tier-2
ISOLATE, so they are not part of the table this clause enumerates - and their bound could not be a
bare mtime TTL anyway: § 3.3 already showed that is unsafe for state that can legitimately go
stale while still alive, which a long-running listener's conf or an active build's log both are.
Both are instead reclaimed by `prune_stale_run_artifacts` (`scripts/lib/state_reclaim.sh`): its
`_LOG_RETENTION_DAYS` mtime bound (that constant owns the number; never restate it) PLUS a
lease-registry reachability guard (`_leased_db_names`) - stale by age AND unreachable from any
leased instance, never by age alone. Called from `55-instance-ops.sh` (`_open_log`, every build)
and `50-instance-spinup.sh` (every listener spin-up); the conf contract itself is
`docs/reference/INSTANCE-ALLOCATION.md` § 6.2, not restated here. This keeps § 3.1/§ 3.2's
exhaustiveness claim true (exhaustive over the ISOLATE table, which `logs/`/`conf/` are not in).
