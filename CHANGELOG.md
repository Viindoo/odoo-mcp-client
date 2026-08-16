# Changelog

All notable changes to the Odoo MCP Client are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [4.26.0] - 2026-08-16

Every session that ended printed `SessionEnd hook [...session-end-gc.sh] failed: Hook cancelled`. The
script never failed - it exits 0 unconditionally - so the message was the CLI aborting the hook, and
the abort was not cosmetic: it KILLED the reaper mid-run. The persisted candidate log was left 0
bytes on every session, which means the discovery half wired up in 4.24 had never once completed,
and a real multi-orphan crash - the case this backstop exists for, where gc spends up to 10s of
SIGTERM grace per orphan - had no chance of being reclaimed in the time actually granted.

### Fixed

- `odoo-ai-agents` - **the SessionEnd crash backstop no longer runs under a budget the CLI does not
  honour.** Measured on Claude Code 2.1.233: a SessionEnd hook is aborted roughly a second after the
  batch's other hooks finish, whatever `timeout` its registration declares (3 runs of 3; the same
  2.2s run completed cleanly once a slower sibling hook was added to the batch, so the budget is
  relative to hooks this plugin neither owns nor can see). `hooks/session-end-gc.sh` now has two
  roles: the hook role validates and spawns, returning in milliseconds, and a detached worker does
  the actual `gc` + list-only `reap-orphans` in its own session, so it outlives both the hook and
  the CLI. The candidate log now lands complete instead of truncated to zero.
- `odoo-ai-agents` - **the reaping's bounds are sized for the work instead of for a hook budget.**
  The previous inner bounds could not fit under the outer one they were documented as matching:
  25s (gc) + 15s (reap-orphans) against the 25s the registration granted the whole script, so a gc
  that actually used its bound guaranteed the rest was cut off. With the work detached, the worker's
  own bounds are the only real limit and are set for a multi-orphan reclaim; the hook's `timeout`
  drops to 10s because all it now bounds is one spawn.

## [4.25.2] - 2026-08-12

4.25.1 made the polling verdict and the run's own verdict agree on the two values it had been caught
getting wrong. It left the third unmapped. A run whose own verdict is `inconclusive` - a tag filter
that matched no test, or a suite whose every matched test was skipped - was still reported to a
polling caller as a successful build. That verdict exists precisely to REFUSE to claim a pass without
proof the suite ran, so reporting it as success overturned the refusal and handed back the same
false green this line of work exists to remove.

### Fixed

- `odoo-ai-agents` - **every verdict a run can publish is now mapped deliberately.** `passed` is a
  success, `failed` is a failure, `inconclusive` is its own terminal outcome that is neither, and an
  unrecognised value is a failure. An unknown verdict means the scanner has fallen behind the
  emitter, which is a defect - reporting it as benign is how this bug kept returning, so it fails
  loudly instead. `BUILD_RESULT=inconclusive` is final: never waited on again, never green.
- `odoo-ai-agents` - **a skip-only run can no longer be certified from its ran-marker.** Before the
  verdict line lands, a run whose every test was skipped publishes the era-correct "the suite ran"
  marker with a non-zero total and no failure anywhere, and the polling path certified success from
  it while the run's own path withheld one. The two paths now share a single definition of a skip
  marker, so a skip-blind path can no longer disagree with a skip-aware one.

- `odoo-ai-agents` - **a coder no longer writes nothing when the change cannot carry a test.** Both
  leaf coders refuse to write without a RED test, which is correct for a behaviour change and wrong
  for work that has no failing state by nature - a comment-only edit, a rename inside prose, pure
  formatting, a docs or translation-text change. There was no way for a caller to say so and no way
  for the leaf to accept it, so such a dispatch returned having produced nothing. A caller now
  declares the exemption by category and names what cannot go red; the leaf holds it VOID the moment
  the work needs an edit a runtime observes, so a behaviour change is still refused without a test
  even under a wrongly declared exemption. An exemption is never inferred from an absent or
  malformed field, and an unresolved test path is never laundered into one.
- `odoo-ai-agents` - **a refusal is now loud.** Any gate that stops a coder before it writes - the
  test gate, the brief self-check, any other precondition - must end in a terminal status naming the
  field that failed and the concrete referent that failed it. The final message is the only channel
  back to a launcher, so an almost-empty one was indistinguishable from success.
- `odoo-ai-agents` - the coordinator's forward list dropped `MODULE SCOPE`, `REQUEST` and
  `ODOO VERSION`; a coordinator following it literally handed a coder no module path, no request
  text and no version. The list is replaced by literal dispatch briefs carrying all three.
- `odoo-ai-agents` - **a worker can never reach the agent that launched it, and the contract now says
  so in terms a worker can act on.** Three things look like a way back up and none is: the sender
  label on an inbound message is an agent TYPE, not an address; no name-to-address lookup exists for
  a worker at any depth; and a send to the root conversation is ACCEPTED and delivered - to a
  conversation that is not waiting, while the launcher that is waiting stays parked. The contract
  previously listed that last one among the sends that fail, so a worker that tried it saw success
  and reasonably concluded the rule was wrong. A send that returns success is not evidence of a
  return path.
- `odoo-ai-agents`, `git-toolkit` - **a coordinator may no longer launch a worker and end its turn to
  wait for it.** Only the root conversation is ever resumed; below it, ending a turn to wait is a
  permanent stall with no error and no output. A dispatch whose result is needed must block. Five
  sites still instructed the opposite, including one whose branch could never have worked because
  the agents it governs are always dispatched.
- `odoo-ai-agents` - **the launch a nested coordinator must not make is now refused, not merely
  forbidden.** The rule above lived in prose and in tests that read prose, so a coordinator that
  ignored it still stalled. A PreToolUse hook now denies the spawn tool outright when the caller is
  itself a subagent and the launch would be backgrounded - which includes omitting the flag, because
  background is the tool's own default and omitting it is the common shape a check keyed on an
  explicit `true` would wave through. The refusal is actionable rather than a scolding: it names the
  blocking re-issue, states that several blocking launches in one message still run concurrently,
  and names the consequence being prevented. The root is never denied, no other tool is ever
  touched, and any payload the hook cannot read fails open.
- `odoo-ai-agents` - a caller can now recognise the stall: a result announcing that work was
  dispatched in the background and will be awaited carries no terminal status, and is to be read as
  STALLED - re-dispatched as a blocking launch or rolled up as blocked, never counted as done.
- `odoo-ai-agents` - **a dispatch that names a worktree now hands down the resolved state dirs.**
  The per-module coordinator's two worker briefs named a worktree but not `SHARE_DIR`/`ISOLATE_DIR`,
  so each worker resolved them itself - after changing into that worktree. The isolate root keys on
  the enclosing git toplevel, so coordinator and worker wrote to two different worklog trees and the
  read-back returned nothing, silently. The requirement existed only as unnumbered prose, which is
  why every brief that filled the numbered skeleton faithfully reproduced the omission; it is now
  part of the worktree field itself, and eleven further dispatch sites that had the same gap carry
  the resolved values too. A worker handed them substitutes them instead of resolving again. Two
  briefs also spelled the worktree key by a name nothing greps for.
- `odoo-ai-agents` - **a worker writes its decision log before every exit, not only a successful
  one.** A refusing worker is never resumed; its replacement is spawned cold and inherits exactly
  what is on disk. The partial edits survived, but the analysis behind the refusal did not - the
  append was gated on reaching green, and the one-line blocked reason carries none of it. Every
  terminal status now owes an entry, and a refusal records what was attempted, what was ruled out
  and why. The test author, which read the log and never wrote one, now writes one too.
- `odoo-ai-agents` - **a refusal no longer pre-empts the list of what it produced.** Both leaf coder
  templates hardcoded an empty list on the one status where partial work is most likely, and no
  caller was told to read it. A refusing worker now lists what it genuinely wrote, its log entry
  included, and the coordinator reads that list and the entry it names before composing the
  replacement's brief. An empty list stays correct when nothing was written.

### Added

- `odoo-ai-agents` - `PRIOR ATTEMPT` is registered as a Coder-family brief field: on a re-dispatch
  that supersedes a failed pass, what that pass returned or omitted plus the log entry it left. It
  existed at a single use site and was unknown to the family whose retry loop needs it, so every
  replacement re-derived what its predecessor had already ruled out.

- `odoo-ai-agents` - a structural guard: the verdict values the result parser can emit and the values
  the polling scanner explicitly maps are both read out of the source and required to be equal in
  both directions. Adding a verdict value without wiring it fails; leaving a mapping for a value
  nothing emits also fails. A fallthrough can no longer absorb a value nobody considered.
- `odoo-ai-agents` - the brief-field lint now walks agent-to-agent dispatch edges, not only
  skill-to-agent ones. The edge that actually carries the coder's test path was checked by nothing,
  while the rule reported four findings against a skill that does not dispatch that edge at all.

## [4.25.1] - 2026-08-12

4.25.0 was verified by driving the plugin against a live instance and a corpus of real run logs.
The database fixes held. What the same exercise showed is that the release shipped TWO functions
that both decide whether a run failed, from the same log, using different rules - so they could
return opposite verdicts for the same bytes. One keyed on the ERROR log-LEVEL column, which Odoo
writes for reasons that have nothing to do with the build, so it called a healthy run failed within
seconds of the first unrelated line; the other never matched the run's own verdict line, so a log
saying the tests failed was reported as a successful build. This release makes the two agree, and
gives a polling caller evidence that actually moves while a suite is running.

### Added

- `odoo-ai-agents` - `wait-log` now emits `BUILD_PROGRESS=markers:<n>|bytes:<m>` on every path.
  Both components are always present: the marker count is what the run itself published, the byte
  length is the fallback that keeps moving when a single long test publishes nothing. A reading is
  evidence of a stall only when BOTH components are unchanged, which is what makes a stopped run
  distinguishable from one still working. It is computed before any verdict branch and can never
  become an outcome.

### Fixed

- `odoo-ai-agents` - **the polling verdict and the run's own verdict can no longer contradict each
  other.** For a test run, terminal failure now means the run's own `TEST_RESULT=failed` line, or a
  hard abort proving the process died. A per-test failure, and the traceback that follows every one
  of them, are mid-run evidence: the suite keeps running past them and the harness appends the
  authoritative verdict when it finishes. Keying a scan on the ERROR log-level column is gone for
  both verbs. Grounded in the Odoo source across every supported series, and validated against a
  corpus of real run logs rather than authored ones.
- `odoo-ai-agents` - **a poller no longer reports a healthy long build as stopped.** The previous
  progress evidence was pinned to a line that never changes once tests start, so a run that had
  been working for many minutes looked identical to one that had died, and the stall rule the agent
  was told to trust was not evidence at all.
- `odoo-ai-agents` - **a log that does not declare its verb now resolves to the narrower test
  predicate.** The install predicate certifies success from a completion marker that lands before a
  test suite starts, and rules failure on a lone traceback: on a test log the first is a false pass
  and the second a false failure. Logs written before the verb stamp existed are the reachable case.
- `odoo-ai-agents` - **the failure counts and the findings file no longer contradict the verdict.**
  When the only failure signal is an aggregate line, the counts are read from it instead of being
  reported as zero, and a count no marker can measure is reported EMPTY, never `0`. The findings
  file is written from the verdict, so it can no longer state that nothing failed for a run that
  did. The agent is told what an EMPTY count means where it will read it.
- `odoo-ai-agents` - the agent and skill prose now state the verb distinction the harness enforces,
  so an agent reading only the instructions reaches the same conclusion the script does.

## [4.25.0] - 2026-08-11

4.24.2 was verified by driving the plugin against a live Odoo 17 instance. The ephemeral-isolation
fix held - but the same run showed a real `run-tests` still dying mid-build with a raw psycopg2
traceback, and a teardown that could not clean up after itself. The cause was not the fix: on a host
where PostgreSQL runs only in a container, nothing the plugin could reach was able to authenticate
as Odoo does, and nothing checked before launching. This release closes that, and makes the failure
an early refusal that names its own remedy instead of a crash.

### Added

- `odoo-ai-agents` - **passwordless local authentication as a setup step** (`48-db-local-auth.sh`,
  wired into `/odoo-ai-agents:odoo-setup` behind its own confirmation gate). It inserts one narrow,
  delimited rule into a LOCAL cluster's `pg_hba.conf` - the declared role only, a single address
  only - reloads, and proves the result by reconnecting the way Odoo does. `revert` removes it and
  restores the file byte for byte. Nothing is stored: the plugin now writes no credential anywhere.
  Which arm runs is decided by where the SERVER is, not by which client binaries this host happens
  to have: one container publishing the declared port is edited even on a host with `psql`
  installed; two publishers is refused and both are named; a genuinely native server is only
  ADVISED, never edited, and there is no flag that makes it sudo.
- `odoo-ai-agents` - `odoo_db.py preflight` and `allocator.py db-preflight`: one primitive that asks
  the question the build itself will face, over Odoo's own connection, and owns the refusal text so
  no caller re-words it.

### Fixed

- `odoo-ai-agents` - **a build no longer crashes when Odoo cannot reach the database.** Every build
  verb now refuses BEFORE opening a log and before launching `odoo-bin`, distinguishing three
  states: the cluster refused our credentials, the cluster never answered, and we could not tell.
  Only the first two refuse; an undeterminable state never blocks. Grounded in Odoo's own startup
  path, which opens a connection for every `-d` name before any module loads on every series 9
  through 19 - so authentication was always a precondition of every verb, never just of create.
- `odoo-ai-agents` - **a truncated `pg_hba.conf` could be committed while the step reported the file
  was intact.** Found in review, reproduced: a write bounded by a timeout kills the local client, but
  the process inside the container keeps its half-written file and commits it. The container side now
  counts the bytes it received and refuses the rename on a mismatch, and a failed write no longer
  asserts anything - it re-reads the file and reports which of four states it actually found.
- `odoo-ai-agents` - **a probe could outlive the bound meant to cut it off.** Signalling only the
  direct child left the real client running as a grandchild holding the output pipe: a 3-second
  bound measured 30 seconds, and the late output was still delivered alongside the timeout status.
  Bounded calls now signal the process group. Five orphaned probes from earlier runs were found
  alive on the development host, each burning a core for 22 hours.
- `odoo-ai-agents` - **an unrelated server error was reported as an authentication failure.** The
  classifier asked only whether a password could be resolved, so on a trust-auth host with no
  password file every unclassified error - too many connections, a cluster still starting, a missing
  database, out of memory - became "Odoo cannot authenticate" and blocked the build with a remedy
  that could not help. Measured against a live cluster: at connection time psycopg2 reports no
  SQLSTATE at all, even for a genuine password failure, so the classifier now requires positive
  evidence and names the server-reported causes it must not claim.
- `odoo-ai-agents` - the locale pin that keeps message matching stable was defeated by `LC_ALL`, so
  on a non-English host a real denial degraded to "could not tell" and the build proceeded.
- `odoo-ai-agents` - the setup step asked the Odoo role to reload the server, but that is
  superuser-only. On the ordinary developer cluster - a plain `LOGIN CREATEDB` role - the file was
  rewritten and the reload then failed, leaving the cluster permanently half-configured. The reload
  and the rule queries now run as a confirmed superuser, and the step refuses BEFORE editing when it
  cannot find one. "Not permitted" and "not available" are no longer reported as the same thing.
- `odoo-ai-agents` - a failed drop that never reached the server is retried over the declared client
  surface instead of being reported as a genuine failure, so an ephemeral lease on a container-only
  host can be released. A release that finds its database already gone now also removes the
  filestore, which neither reaper could have found afterwards.
- `odoo-ai-agents` - `release --force-forget` and the plain release path name their outcomes
  distinctly, so "abandoned" means a database really was left behind.
- `odoo-ai-agents` - refusals no longer name a remedy that cannot apply: a stopped cluster is told to
  start, not to reconfigure authentication; a managed or remote cluster is told about
  `ODOO_PG_PASSWORD`, which is the only thing that works there.
- `odoo-ai-agents` - the pg_hba rule builder refused the role `all` but accepted `+role` (every
  member of a role) and `@file` (every role named in a file), and accepted malformed IPv6 literals
  that would have made the whole file unparseable.
- `odoo-ai-agents` - the agent contract now covers all four acquire refusals rather than two, keeps
  the operational status enum and the continuation status enum from being confused for each other,
  states that an undeterminable state never blocks, and tells the agent to route the `pg_hba.conf`
  step through the human rather than invoking it itself.

### Changed

Two behaviour changes worth reading before upgrading:

- An acquire that succeeded before can now refuse, with exit `8` (the cluster refused our
  credentials) or `9` (the cluster never answered), for `--mode ephemeral` and `--mode exclusive`
  alike. Only a PROVEN refusal blocks; `--no-create`, `readonly` and `shared` are never gated. The
  remedy is named in the message.
- The plugin now edits a file it does not own, on a running server, when you ask it to. It is
  reversible, gated behind a confirmation, refuses when any published binding is not loopback,
  refuses when it cannot find a superuser to reload with, and backs up before replacing. A genuinely
  native server is only advised.

## [4.24.2] - 2026-08-10

4.24.1's two fixes were verified by actually driving the plugin against a live Odoo 17 instance.
The verification passed - and exposed five further defects, all one story: a throwaway instance was
not actually isolated, and nothing reliably noticed when a run finished or a resource was left
behind. Every fix here came out of that run, not out of a code read.

### Fixed

- `odoo-ai-agents` - **`--mode ephemeral` silently handed back the declared, long-lived database.**
  The CREATEDB probe shelled out to `psql`; on any host where Postgres runs only in a container
  there is no libpq client on PATH, so the probe always failed and the allocator quietly reassigned
  the request to `exclusive` mode on the shared database - the exact opposite of the isolation
  ephemeral exists to provide. The role genuinely had CREATEDB the whole time. The capability is now
  answered by a query over the connection Odoo itself resolves, so no client binary is involved, and
  an `ephemeral` request has exactly two outcomes: it succeeds as ephemeral, or it writes no lease
  and refuses with exit `6` (the role lacks CREATEDB) or `7` (the capability is undeterminable).
  Closes #212.
- `odoo-ai-agents` - **the replacement probe could hang forever.** It ran with no time bound, and
  Odoo's own connection layer sets no libpq timeout on any series, so a paused or firewalled cluster
  made `acquire` return nothing at all - no lease, no verdict, no exit code. Worse than the wrong
  answer it replaced. Every Postgres-touching probe is now wall-clock bounded under one policy, and
  "could not answer in time" is reported as undeterminable, never as a factual no.
- `odoo-ai-agents` - **a docker daemon error was recorded as a durable fact.** Detection discarded
  the exit status, so "I could not ask" and "no container publishes that port" were indistinguishable
  and both were written to the catalog as `tcp-only`. Running setup before starting the cluster
  poisoned the catalog until someone re-ran registration by hand. Ambiguity now refuses and writes
  nothing; a stopped-but-publishing container is named instead of silently misfiled.
- `odoo-ai-agents` - **the function whose only job was bounding a probe could spin forever.** A
  zero-padded timeout hit bash's octal parsing, the comparison never became true, and the loop ran
  unbounded with the child alive. The bound is now wall-clock based and a non-numeric bound refuses.
- `odoo-ai-agents` - **a failed raw database drop deleted the lease while the database survived**,
  creating an orphan that `reap-orphans` can never find, because it excludes any database a lease
  references. A lease whose environment predates this release is now re-resolved from the current
  catalog at release time, with `release --force-forget` as a documented, loud escape.
- `odoo-ai-agents` - **a value containing `"` or `\` made the host's instance catalog unparseable**,
  silently and with a success exit. Every consumer - allocator, all five setup steps, the teardown
  hook - then failed until a human repaired the file by hand. Values are escaped and the catalog is
  published atomically.
- `odoo-ai-agents` - **the instance agent stopped waiting and reported nothing.** A real blocking
  helper existed but the prose called it "preferred", never overrode the harness's own do-not-poll
  default, and the skill file dropped its name entirely - so the agent ended its turn on prose while
  the build had already finished, and a human had to read the log and feed the result back. The
  blocking foreground call is now mandatory and spelled out, and both files state it identically.
- `odoo-ai-agents` - **the wait could report success before the tests ran.** `Modules loaded.` is
  logged before post-install tests start, and the waiter scanned no test marker at all. Logs now
  identify the verb that wrote them and the waiter resolves the matching terminal signal.
- `odoo-ai-agents` - **the teardown gate only fired on a literal `status: DONE`.** An agent that
  ended its turn with no status at all sailed through and leaked a lease, which then blocked every
  concurrent acquire on that database until a one-hour TTL expired. The gate now blocks any turn end
  that neither reports a stopped run nor forwards a named handoff.
- `odoo-ai-agents` - **a per-module test verdict was decided by other modules' tests.** Odoo's
  auto-install fan-out pulled dozens of unrelated modules into a single-module verification. The run
  is deliberately NOT narrowed - suppressing tests manufactures a false green - but the scope is now
  reported: modules actually installed and tests actually run come back as facts, and a verdict
  decided outside the module under verification says so.
- `odoo-ai-agents` - a setting documented with a default that no code anywhere read has been removed.

### Changed

Three behaviour changes a patch label does not advertise on its own:

- `--mode ephemeral` acquires that succeeded before can now refuse. Exit `7` fires for an instance
  whose catalog entry predates this release on a source checkout, and for a container-run Odoo that
  declares no interpreter. The remedy is named in the message: `45-venv.sh record-env --series <X.Y>`.
  `--no-create` remains a probe-free escape.
- The teardown gate widened from `DONE` to every turn end except a `BLOCKED`/`NEEDS_CONTEXT` report
  or a forwarded `INSTANCE_HANDLE`. A subagent that used to end on a bare `NEEDS_NEXT`, or on no
  status, is now blocked while it still holds a live lease.
- `instances.toml` gains `db_run_mode`, `db_container` and `odoo_root`, written automatically at
  registration; `release` and `gc` can now legitimately fail and keep a lease where they previously
  always reported success.

## [4.24.1] - 2026-08-10

Two defects with one root cause: the plugin instructed executing agents to do things the platform
underneath them does not support, and then built contracts, prose, and guard tests on top of the
pretence. The instance harness ran Odoo at `--log-level=warn`, where a PASSING test run emits
nothing at all - so it could not tell "the suite passed" from "the suite never ran". Separately,
every dispatch brief carried a `CALLER_ID`/`REPLY_TO` reply address that no agent could ever obtain,
because the launch call has no `name` parameter and the agent roster never contains your launcher.
Both are fixed by deleting the impossible machinery rather than documenting around it, which is why
this release removes far more prose than it adds. It stays PATCH: the removed brief field never had
an obtainable value, so nothing that worked before stops working.

### Fixed

- `odoo-ai-agents` - **a passing Odoo test run is no longer invisible.** The build/test default is
  now `--log-level=info` (Odoo's own default on every series 8.0-19.0). The summary line
  `F failed, E error(s) of N tests` is emitted at INFO when a run passes with more than zero tests
  on every series through 19.0, so at `warn` a green run was silent and indistinguishable from a
  suite that never executed. `runbot` is not an alternative: it is a hard CLI failure on 8.0-13.0
  and still suppresses the passing line where it exists. `test` is not an alternative either - it
  has no `PSEUDOCONFIG_MAPPER` entry on any series and is provably a no-op synonym for `info`.
- `odoo-ai-agents` - **a test run that only had failures was reported GREEN on six of twelve
  supported series.** The result parser matched `failed`/`error` but never `failures`, so the
  8.0-13.0 wording `Module m: 2 failures, 0 errors` scored `passed`. Failure detection is now
  version-general, and a pass additionally REQUIRES a positive era-correct "tests ran" marker
  instead of being the fallthrough - a run that proves nothing now reports `inconclusive`.
- `odoo-ai-agents` - **the honest verdict was being discarded one layer up.** The `run-tests`
  contract derived its status from four counters and never read `TEST_RESULT=`, so a suite that
  never ran (all counters zero) resolved to `tests-passed` for every gate role. The ladder now
  reads `TEST_RESULT=` first and lets it outrank the counters.
- `odoo-ai-agents` - `--log-mode warn` is refused at the flag (exit 2). It suppresses the same INFO
  summary, so every green run under it parsed as `inconclusive`.
- `odoo-ai-agents` - install failure during a test run classifies as `failed`, not `inconclusive`,
  and is no longer masked by an otherwise-green ran marker.
- `odoo-ai-agents` - the log retention sweep is scoped by the existing lease registry, so it can
  never delete the log of a live instance; an unreadable registry sweeps nothing.
- `odoo-ai-agents` - a zero-padded series (`08.0`, `09.0`) no longer selects the wrong era. The
  all-digit check passed it through to bash arithmetic, which rejects `08` as invalid octal and
  silently fell through to the modern branch - wrong log namespace and wrong result marker for v8
  and v9.
- `odoo-ai-agents` - `Registry loaded` is gone as a progress marker. It does not exist before Odoo
  15.0; the replacement marker is present on all twelve series.

### Changed

- `odoo-ai-agents` - **an agent's final message is now the ONE return path to its launcher**, declared
  once in `snippets/spawner-completion-contract.md` R3. A child never messages its launcher; the only
  address anyone holds is a CHILD'S, captured from that child's own launch return; literal `main` is
  reserved for a background agent `main` itself launched, mid-run only. Every other file cross-
  references R3 instead of restating it.
- `odoo-ai-agents` - the universal dispatch-brief skeleton goes from 11 fields to 10: the reply-address
  field is retired, not renamed. Briefs that still carry one are malformed and the field is ignored.
- `git-toolkit` - `SendMessage` and `TaskUpdate` are no longer granted to the three leaf agents. A
  listed-but-ungranted tool made the model call it and error rather than cleanly fall back.

### Removed

- `odoo-ai-agents` - `snippets/agent-team-protocol.md` and its `references/` copy. Once the
  unobtainable addressing, the capability probe that could not succeed, and the duplicated rules were
  taken out, nothing implementable remained.
- `odoo-ai-agents` - the "Agent Team mode is active" self-check in all 26 agents. It inferred a mode
  purely from a messaging tool being present in the toolset, which is true on every ordinary run, so
  it fired as a false positive every time.

## [4.24.0] - 2026-08-07

Project identity used to be cached to a `context.md` file that nothing on any machine had ever
actually produced. It is now resolved per fact through an ordered, terminating ladder instead of
being cached at all - the declared instance catalog already carried the series and profile, so the
cache was shadowing a source of truth that already existed. This release removes a registered
skill and a cited snippet, which would normally be MAJOR, but the removed artifact had zero real
dependents, so nothing breaks in practice; it stays MINOR.

### Added

- `odoo-ai-agents` - `snippets/project-facts-resolution.md`: an ordered, terminating 5-rung
  precedence ladder for the four facts every Odoo task needs (series, OSM profile, module/addons
  scope, instance target) - the dispatch brief, then the declared instance catalog, then the
  checkout on disk, then the caller's own words, then one batched ask. Resolution is PER FACT: an
  unanswered fact keeps descending the ladder while a fact already answered by an earlier rung
  stays authoritative and is never re-asked.
- `odoo-ai-agents` - `scripts/lib/odoo_series.py detect`, a new derivation that reads the Odoo
  major series from a checkout via core `release.py` or a series-named git branch, falling back to
  an explicitly weak, unconfirmed manifest-version hint or an era range rather than ever guessing.
  Rung 3 of the resolution ladder above.
- `odoo-ai-agents` - `scripts/lib/instances_io.py locate`, a new subcommand that maps a repo path
  to its declared `[[instance]]` (longest covering `addons_path` entry wins, ties break to the
  highest series), plus `scripts/lib/resolve_instances.sh --path` so the ladder's rung 2 has one
  documented, runnable invocation instead of a source-then-call two-step.
- `odoo-ai-agents` - `tests/test_context_md_removed.py`, a whole-tree guard with two layers: the
  removed artifact names under any spelling, and the underlying MECHANISM (an instruction to read
  or persist project facts from a file under the state dir), so a re-introduction under a
  different filename is caught too.

### Changed

- `odoo-ai-agents` - **`scripts/lib/instances_io.py read` now emits `INST_SERIES` where it
  previously emitted `INST_VERSION`.** The catalog's own key has always been `series`; `read` and
  the new `locate` subcommand simply disagreed on what to call it on output, and `locate` needed
  the correct name from the start. This is a MINOR release, so semver alone will not warn anyone -
  if you `eval` this script's output and read `INST_VERSION`, you will now silently get an empty
  string; switch to `INST_SERIES`.
- `odoo-ai-agents` - `scripts/lib/instances_io.py read` and the new `locate` now distinguish a
  catalog that is present but unparseable TOML (new exit 3, with one stderr line naming the file)
  from a genuine "nothing declared here" miss (exit 1, silent). Previously a typo'd catalog was
  indistinguishable from no catalog at all.
- `odoo-ai-agents` - `snippets/upg-conventions.md` Convention 1 (no version bump on a code-level
  upgrade) is now a CORE rule applied on every distribution; it was gated to
  Viindoo-profile-only while the rule that invoked it declared itself CORE, so on any other profile
  it could never fire. Added the missing remedy: a manifest `version` that already carries a
  series prefix is CONVERTED to the short form by dropping the prefix - a conversion is not a bump.

### Fixed

- `odoo-ai-agents` - the Odoo series derived from a checkout was wrong on every indexed series: a
  short manifest `version` (`1.3`, `1.0.9`, `1.0.0`) was being read as the series, when it is
  always the addon's own version number. A manifest `version` is no longer treated as series
  evidence at all - `odoo_series.py detect` surfaces it only as an unconfirmed hint, because a
  code-level upgrade leaves it unbumped, so it can name an earlier series than the checkout.
- `odoo-ai-agents` - v8.0/v9.0 blindness across the plugin: the module descriptor is
  `__openerp__.py` before Odoo 10.0 and `__manifest__.py` from 10.0 on, and the core package
  directory (`openerp/` vs `odoo/`) flips at the same boundary. Discovery globs, descriptor reads,
  and descriptor writes now handle both. The write axis mattered most: writing a fresh
  `__manifest__.py` into a module that already has `__openerp__.py` creates a stub that silently
  shadows the real descriptor, dropping every model, view, and dependency it declares with no
  error.
- `odoo-ai-agents` - `scripts/lib/discover_odoo.sh` found no addon repos on a v8/v9 host (it
  globbed `__manifest__.py` only), so the instance catalog could never be populated from one.
- `odoo-ai-agents` - the `odoo-modules-upgrade` duplicate-module gate scanned at the wrong
  directory depth (`-maxdepth 1` against addons-path entries, where a descriptor actually sits at
  depth 2) and so always reported "no duplicates" without examining a single module. Also widened
  to glob both descriptor filenames, matching the v8/v9 fix above.

### Removed

- **`odoo-onboarding` skill and the `context.md` project-context artifact it produced, plus the
  `snippets/context-bootstrap.md` snippet that bootstrapped it.** Project facts (series, profile,
  module scope, instance target) are now resolved per fact through the ladder in
  `snippets/project-facts-resolution.md` instead of being cached to a file - the instance catalog
  already declared the series and profile, so the cache was shadowing an existing source of truth
  and could go stale against it. Skill count 52 -> 51.

## [4.23.0] - 2026-08-07

A live review of the SHIPPED 4.22.0 - the build actually loaded in a running session, not a working
tree - found that its fixes had landed but that everything which survived sat in a surface the sweep
had excluded from scope: YAML frontmatter, `commands/`, `docs/personas/`, the reference doc's worked
example, and a registry field the lint compared against itself. The previous release's lesson was
that prose alone cannot hold a rule; this one's is that a correct rule still fails if the sweep that
applies it misses where the rule is read. Each fix below therefore ships with a guard over the
surface it just corrected.

### Added

- `odoo-ai-agents` - four guards over surfaces nothing checked. No tier or vendor model-tier token in
  any frontmatter `description` - the existing tier guard scanned fenced template blocks and
  structurally could not see frontmatter, proven by importing its own extractor and showing it
  returns nothing for a description carrying all four tokens. Every gate-reply string in the whole
  tree, not only in `workflows/`, drawn from the two sets declared in `snippets/vocabulary.md` and
  parsed from that file rather than hardcoded. The terminal stage order stated in exactly one place,
  with the canonical stage list parsed from the owner's own block so adding a stage does not require
  editing the test. And a registry claim that a skill touches a live instance backed by evidence in
  the skill itself. Each is proven able to FAIL against the shipped release, not merely observed to
  pass.

### Fixed

- `odoo-ai-agents` - a resumed run could open a second pull request for the same repository. A node
  is marked running before it is dispatched, the resume path skipped only completed nodes, and no
  check for an already-open pull request existed anywhere - so the land step re-ran and asserted, as
  a fixed string, that its branch had never been pushed. A running node now means dispatched with an
  unknown outcome and is reconciled against observable state before anything is repeated, and the
  land step derives whether this is a first push instead of claiming it, updating an open pull
  request rather than opening another.
- `odoo-ai-agents` - the Vietnamese persona document still taught one squashed pull request per wave.
  Its English sibling had been corrected; no commit had ever touched `docs/personas/`, because the
  original survey classified that directory as human-facing and excluded it. For a Vietnamese-reading
  team it is the document actually consulted.
- `odoo-ai-agents` - a repository's id in the run file was defined circularly while the field beside
  it had a full resolution rule, so two ids naming one repository produced two pull requests and the
  audit called it correct. The id now derives from the normalized remote URL, making it a property of
  the repository rather than of a checkout, and two entries resolving to one id are one repository.
- `odoo-ai-agents` - `repo: null` let a lifecycle node sit outside every repository's readiness scope,
  so a pull request could open with acceptance and documentation never having run. It is now legal
  only for work that writes into no repository and gates no delivery, re-derived by both the plan
  serializer and the driver from one predicate.
- `odoo-ai-agents` - two skill descriptions still named vendor model tiers and internal gate tiers.
  A description is loaded into every session's skill listing, so these reached the model's context on
  every single run, and neither the release's sweep nor its guard covered frontmatter.
- `odoo-ai-agents` - twelve gate-reply strings outside `workflows/` still used retired keyword sets,
  including in the intake front door and in the reference doc's only complete worked example. One was
  a functional defect rather than a cosmetic one: a command asked for one reply set and branched on a
  word from another, so a user typing exactly what they had been asked hit no branch. The two options
  with no equivalent in the declared sets are now asked as their own questions instead of becoming
  extra keywords.
- `odoo-ai-agents` - the terminal stage order had one declared owner and nine restatements, several
  dropping translation and acceptance entirely, one of them printed on every plan. That disagreement
  is what defeated the two previous attempts at this rule, so the restatements now cite the owner.
  The worked example emitted a documentation node per module against a rule stated two files away;
  the dependencies settle it in the rule's favour.
- `odoo-ai-agents` - a skill that neither provisions nor drives an instance declared that it did, and
  therefore derived the top gate tier, stopping an otherwise automatic run to authorize writing a
  document. The lint could not see it: it compared the stored tier against its own derivation rather
  than against what the skill does. It can now contradict the registry, and ignores the generated
  tool block that would otherwise have vouched for the claim. Three orchestrators that push branches
  and open pull requests now declare that fact, so their top tier rests on the reason that justifies
  it. Entries whose correction would ADD a human gate are reported rather than flipped.
- `odoo-ai-agents` - the run auditor was walked through three times with constructed run files, each
  exiting clean. It audited a declaration rather than the act, so a node opening pull requests while
  declaring another kind was invisible; opening is now read from the pull-request URLs a node
  actually recorded, excluding a node that was handed one and a node that only watches one, with a
  disagreement between declaration and evidence reported in both directions. Its land-tail test
  matched substrings, so a node named after a merge exempted itself; it now matches the node kind
  exactly and never reads a free-text id. A run file it could not parse was certified clean;
  unreadable is now its own third verdict.

## [4.22.0] - 2026-08-06

Four user-reported defects, fixed by changing structure rather than restating rules. Two of them -
the pull request opening before the work finished, and one pull request per wave instead of one per
repository - had already been fixed twice in prose (4.17.1 and 4.20.0) and recurred both times,
most recently on 4.20.3. Each entry below names the structural property that permitted the
behaviour, because a rule stated more firmly a third time was predicted to fail the same way.

### Added

- `scripts/audit-run.py` - asserts over a finished run file what a test suite cannot see: one
  pull-request-opening node per repository, no pull request opened while substantive nodes are
  unfinished, no gate-tier token in any recorded continuation contract, and a human-gate count with
  a per-node breakdown. A green suite proves the shape of the text; it was green throughout both
  previous failed fixes. This is the only check that observes what a run actually did.
- `odoo-ai-agents` - the run file gains `repos[]` and a per-node `repo`, so "one pull request per
  REPOSITORY" is expressible for the first time. Previously the repo capability card was filled once
  per run, nodes carried no repo identity, and the rule could only be stated as "one PR per run" -
  which is wrong the moment a run touches two repositories, and a rule that is wrong for multi-repo
  runs invites improvisation in all of them. One `integrate` node is now keyed per repo, the driver
  resolves its readiness scope from the field instead of describing it, and a node belonging to no
  repository carries `repo: null` explicitly and sits outside every repo's readiness scope. The
  audit checks one landed PR per declared repo and scopes the after-PR rule per repo, so one
  repository's pull request no longer waits on another's unfinished work.
- `odoo-ai-agents` - the context-budget rule resolved its corpus by file BASENAME, and every skill
  file is named `SKILL.md`, so it structurally could not cap any skill - including `run-harness`, the
  most re-entered contract in the plugin, which nothing capped at all. An explicit budget entry is
  now itself an entry ticket and its file is measured wherever it lives. Nine caps that sat above
  their file's real size after trimming are tightened, so reclaimed space cannot silently regrow.
- `odoo-ai-agents` - the orchestration lint scanned `skills/`, `snippets/` and `agents/` only, so
  `docs/`, `commands/` and `workflows/` were invisible to EVERY rule in the file rather than to one
  of them. Those trees are now in scope, with the `docs/` subset derived from what agent-facing
  prose actually cites instead of a hardcoded list. Its provenance rule now covers the vocabulary
  that occurs in practice, with guards that keep Odoo domain-version history, a prospect's incumbent
  system, and operative back-compat instructions passing - a back-compat rule has a live reader, so
  deleting it breaks a consumer, while a note about what this plugin used to do costs context on
  every dispatch and can be read as current fact.

### Fixed

- `odoo-ai-agents` - the run driver loaded the run file once, outside its own loop, so after the
  first iteration every invariant the run depended on survived only in conversational context and
  decayed over a long run. The file is now re-read at the top of every iteration and is the live
  source of truth over anything the agent remembers. Three status mutations that were never
  persisted - two blocked paths and the finalize step - are now written, so a terminal status is
  visible to a resume.
- `odoo-ai-agents` - the terminal `integrate` node had no stated readiness precondition, so with
  `depends_on` under-specified the tie-break was plan authoring order and whether the pull request
  opened before or after the review, doc and acceptance nodes was decided by accident. The driver
  now re-derives the precondition rather than trusting `depends_on`: `integrate` for a repository is
  ready only when every node of that repository outside the land tail is done or skipped. The
  land-tail carve-out is stated as mandatory in the text, because the obvious simplification of it
  deadlocks every run against the monitor node.
- `odoo-ai-agents` - the only worked example plan in the repository placed a doc node inside a
  coding wave and omitted the `integrate` node entirely, so the sole artifact an executing agent
  imitates never showed the step that opens the pull request. The example now carries the terminal
  lifecycle wave in dependency order, the `integrate` node as the one-pull-request opener, a
  repository annotation on every node, and an explicit note locating a second repository's own
  `integrate` node - making one pull request per repository expressible, which it previously was not.
- `odoo-ai-agents` - terminal stage order was restated in five places that disagreed, and two peer
  orchestrators ordered the final code review after the pull request opened while a third ordered it
  before. There is now one Terminal stage order constant with a single owner, and the discriminator
  is stated with it: work that can force a code change runs before the pull request, and only work
  that must observe the opened pull request runs after it. Both inverted reviews read a worktree
  diff, never the pull request, so neither needed it to exist. No review stage was removed.
- `odoo-ai-agents` - the continuation contract carried a `risk_level` field holding a gate-tier
  token, and that block is appended to nearly every visible agent output, so users were shown
  internal tier codes on essentially every turn. No consumer read the field - the driver re-derives
  the tier and forces any unplanned node to the top tier regardless. It is removed rather than
  renamed. Gate prompts now read as plain language, model-tier names no longer appear in questions
  put to a user, and the Odoo Semantic acronym is expanded where a user must act on it.
- `odoo-ai-agents` - design and planning each imposed a scope-preview approval on top of the one
  intake already takes, asking the user to approve substantially the same thing twice; both are
  removed, following the pattern three sibling orchestrators already use. The genuine
  scope-decomposition question is kept. Fifty workflow gates that had invented their own reply
  keywords are normalized onto the two declared sets, and `yes` is retired as a gate reply
  everywhere, including in the mirroring rule that had contradicted the glossary. A chat-only skill
  that calls static tools only no longer declares that it touches an instance, so it stops gating as
  an irreversible action.
- `odoo-ai-agents` - changelog notes, provenance tags and references to files, scripts and agents
  that no longer exist are removed from agent-facing runtime files. The bulk sat in one reference
  loaded on every instance-provisioning dispatch, which still carried the section headings of the
  implementation plan it was written from.
- `odoo-ai-agents` - the coding gate showed the user a `model` column of vendor tier names, which
  say nothing to an Odoo consultant about depth or cost while the choice itself has a real price
  spread. The column now reads `depth` with `quick / standard / deep / deepest` and a one-line cost
  ordering; the raw tier is still recorded in the plan because it drives dispatch, and a fixed
  rendering map keeps the translation deterministic rather than improvised per run.
- `odoo-ai-agents` - a workflow gate reply meaning "show it in chat, do not write a file" had been
  folded onto `skip`, which means something else everywhere else in the plugin. Where the output
  goes is now asked as its own question after approval, so no gate keyword carries a second meaning
  and no third keyword set was introduced.

## [4.21.0] - 2026-08-06

### Added

- `odoo-ai-agents` - a new `SubagentStop` hook records each dispatched agent that stops carrying no
  terminal status, or that leaves a tool call unresolved, so the rate of silently-stopped agents is
  measurable instead of inferred. It fails open: if its dependencies or state directory are
  unavailable, it exits without affecting the session.

### Fixed

- `odoo-ai-agents` + `git-toolkit` - agents carried contradictory rules for whether they could launch
  a child and receive its result; some instructions produced an agent that ended its turn with no
  output and no error, indistinguishable from a normal finish. There is now one rule: an agent
  inspects its own launch capability and branches - no capability means it is at the nesting cap, so
  it works inline or returns; a blocking-launch switch means it launches blocking and gets the result
  in the same turn; no such switch means it launches async and ends its turn to be resumed, never
  polling. An agent must never end a turn with uncommitted work. A stale nesting-depth figure in the
  reference docs was corrected at the same time. Closes #204, #205.
- `git-toolkit` - the toolkit detected each repo's commit-message convention but never enforced it: a
  caller-supplied message reached `git commit` guarded only by a comment, and one skill hardcoded a
  third format of its own and passed it through as a literal. A supplied message is now validated
  against the detected convention, rewritten when the intent is recoverable, and refused when it is
  not; the sign-off is applied by the commit command itself and verified as a post-condition rather
  than assumed up front; and the skill that hardcoded its own format now requests a commit by naming
  the touched files and the business outcome, leaving the message to the toolkit.
- `odoo-ai-agents` - the plugin carried three incompatible status vocabularies and three different
  gate-reply keyword sets, mixed within single files, so an executing agent had to reconcile them at
  every handoff and every gate. One status value was
  emitted by several skills but recognized by neither the continuation parser nor the run loop, so a
  real caveat used to vanish with no signal at all. A single glossary now owns the
  continuation-status enum, both gate-reply keyword sets, and the operative meaning of terms that
  were overloaded across the plugin; consumers point at it instead of restating it.
- `odoo-ai-agents` - twenty-five agents that cannot launch anything were still citing the
  delegation-and-await contract that governs launching, regardless of whether they could spawn
  anything - pulling roughly 640,000 bytes of unusable guidance into cold contexts that could never
  act on it. The citation is now kept only on the coordinator that actually launches teammates, with
  the few clauses a leaf genuinely needed inlined into the brief contracts it already reads.
  Separately, five dispatch briefs sent field names that disagreed with what the receiving agent's
  contract required - in one case every concurrent worker was directed at the same output filename -
  so briefs now carry resolved values and real addresses in place of pointers a callee would
  otherwise have to go resolve itself, and each caller sends the field names its callee documents.
  The hottest shared contracts (`dispatch-brief`, `git-delegation`, `module-coordination-ledger`,
  `agent-team-protocol`, `worker-brief`, `spawner-completion`, `continuation-contract`,
  `worklog-contract`, `test-first-contract`, `instance-handle-contract`, `resource-teardown-contract`,
  `concurrency-guard`, `state-root-resolution`) keep their normative rules in the always-loaded
  snippet and move their rationale/explanation into a companion reference file executing agents are
  never pointed at.
- `odoo-ai-agents` - the SSOT generator's injector stopped regenerating at the first end marker, so a
  file carrying a second marker pair had that region frozen indefinitely and invisible to the
  idempotency check, since nothing was ever written there to diff; a second marker pair is now a loud
  error. In the tool registry, five live capabilities were undocumented, leaving three of them
  unreachable from anywhere in the plugin; several skills called tools their own registry entry
  omitted; two skills declared a far older minimum server version than the tools they actually use;
  and one skill claimed it made no tool calls while making seven. The dependency checker now also
  verifies that every tool named in hand-written prose is declared, ignores tools named only to
  forbid them, and fails by default rather than warning.
- `git-toolkit` - the safety contract required every mutation to run in a dedicated worktree and
  never touch the shared checkout, but gave no compliant way back once a shared checkout had already
  accrued uncommitted work - the only remedy read as a violation, so operators correctly refused it.
  A single narrowly-scoped restore path now exists, still behind the human-confirm gate and still
  requiring proof the work survives elsewhere before anything already in the shared checkout is
  discarded. Separately, the nesting protocol now runs a positional self-check before an agent's
  first mutation, instead of only noticing a drift back to the shared checkout after the fact.

### Changed

- `git-toolkit` bumped 0.6.1 -> 0.6.3 across two intermediate patch cuts (versions independently).

## [4.20.3] - 2026-08-04

### Fixed

- `odoo-ai-agents` - a lint gate could report a clean pass while none of its custom checkers had
  loaded. The whole checker sweep runs inside a single test method, so when the plugins fail to load
  that method still passes with nothing to assert: no failures, no errors, no skips, no warnings, and
  the run resolved to the one verdict that lets a caller proceed with nothing to address. Among the
  checkers silently absent is a SQL-injection check, so the gate was reporting safety it had never
  established. A pre-PR lint run now requires positive evidence in its own log that every installed
  lint-class module's checker set actually loaded; a shortfall, or a log that cannot confirm one, is
  no longer a pass. The containment loop that reacts to a failing pre-PR gate was reacting to only
  one of the non-passing verdicts, so the widened verdict would have slipped through the one gate
  that matters in an unattended run - that is fixed too.
- `odoo-ai-agents` - the git-rebase pipeline had the same shared-commit write race that was fixed in
  forward-port: above its batching threshold it dispatches one extractor per module, and a commit
  touching two modules had both extractors writing the identical intent record with no owner rule.
  Records are now namespaced per module and reconciled by a deterministic owner - the first module in
  the order recorded upstream, persisted so a resumed run cannot choose differently. The extractor's
  own slug fallback, which silently reconstructed the unsafe shape whenever a caller omitted the
  field, is gone: the field is required and its absence is refused. Because that reconciliation is a
  step that can fail to happen, it carries its own resume state, and the first phase that reads those
  records now refuses rather than proceeding when one is missing.
- `odoo-ai-agents` - the setup step that grants the state-root helper its permissions embedded the
  installed version's own directory in the rule, so every upgrade added a rule pair and removed
  nothing. Rules now converge on the current version. The prune is anchored to this plugin's own
  path, not merely to the script name, so a different plugin shipping an identically-named script
  keeps its rule; and when the installed path carries no version segment at all, pruning is skipped
  rather than guessed, because guessing there would widen the match to sibling plugins.

## [4.20.2] - 2026-08-04

### Fixed

Found by walking a three-level dispatch chain - a front-door skill, the per-module coordinator it
launches, and the three workers that coordinator launches - as the executing agents would read it,
with the plugin installed so every pointer resolved to the shipped contract. The previous release's
own gates were green throughout.

- `odoo-ai-agents` - a worker returning `NEEDS_CONTEXT` could hang its whole coordinator, and through
  it every caller above. The coordinator's wait released only on a two-state task-board vocabulary
  (`completed`/`blocked`) that its own cited contract never defined, and that no terminal status
  outside `DONE`/`BLOCKED` could ever reach - so a legally-emitted `NEEDS_CONTEXT` left a barrier that
  never lifted. The release condition is now defined once, against the four Continuation Contract
  terminal statuses, and never against a tool-native label: a `BLOCKED` or `NEEDS_CONTEXT` child is as
  terminal for barrier purposes as a `DONE` one, even where the task tool has no label for the
  distinction. Tool availability varies by context and by grant, so a contract must not depend on it.
- `odoo-ai-agents` - a coordinator that died mid-flight was not merely undetected; it was actively
  reported as healthy. The coordination ledger refreshed a liveness timestamp for every module the run
  believed it was building, and its lifecycle had no transition for a dispatch that returned no status
  at all, so a dead build kept advertising itself to other runs. The accounting now recognises that
  case rather than inventing a polling loop.
- `odoo-ai-agents` - an instance whose owner process was alive and healthy was destroyed once its
  lease TTL lapsed: process group killed, ephemeral database dropped, work in progress lost. Owner
  liveness could only condemn a lease, never protect it. Liveness is now authoritative - a same-host
  owner pid whose recorded process-start fingerprint still matches protects its lease regardless of
  TTL, and needs no heartbeat to survive. A dead pid, or one positively recycled onto another process,
  still condemns immediately. TTL now governs only the residual case where liveness cannot be verified
  at all, and its default is reduced accordingly. The same defect existed a second time, in the shell
  mirror of that check inside the teardown hook, and is fixed there too. The bias is stated in the
  code: an un-reaped orphan costs memory, a wrongly-reaped lease costs the owner's work.
- `odoo-ai-agents` - the deep-survey pointer reached the per-module coordinator and stopped there. The
  coordinator's own self-check demanded the field, but the enumeration it follows when briefing its
  workers named six fields and omitted it, so the grounding a human handed over never reached the
  agents that needed it - including the one that authors the failing test, which could not name the
  field at all.
- `odoo-ai-agents` - six sites in the forward-port pipeline described the per-module intent record
  with its path segments in the wrong order, contradicting the write path shipped in the same release.
  One of them was the crash-recovery instruction, so a resumed batch searched a directory shape that
  never existed and concluded there was no prior work. A guard now fails when one logical path is
  described two different ways anywhere in the tree; it deliberately does not decide which order is
  correct, because before this fix the wrong order was the majority.
- `odoo-ai-agents` - three guards were closed-class enumerations that passed their own tests while
  missing every phrasing outside the list. Each now keys on the property it is actually testing rather
  than on incidental vocabulary, and each was verified against constructed bypasses.
- `odoo-ai-agents` - a rule changed at its definition site left restatements behind in four further
  places, which then disagreed with it. All four are now pointers, and two guards fail when a
  restatement diverges from the source it cites.

## [4.20.1] - 2026-08-04

### Fixed

Every item below was found by exercising the plugin as an INSTALLED plugin, so `${CLAUDE_PLUGIN_ROOT}`
and the Skill tool resolved to the shipped contract rather than a working copy. All of it was present
while the full test suite, the schema validators and the generator idempotency check were green -
gate colour is not evidence that a runtime agent is driven to the right behaviour.

The dominant defect class was a mechanism that is fully described and never reached. It appeared
three times independently, and each instance is fixed at its wiring, not at its description:

- `odoo-ai-agents` - `scripts/lib/allocator.py reap-orphans` existed, was tested, and was called by
  nothing: the session-end hook ran only `gc`, which by its own documentation cannot see the class
  reap-orphans was written for. Its discovery half now runs from that hook and records candidates;
  the destructive half stays a deliberate human action, because an unattended crash-time sweep across
  a whole cluster is a worse risk than the leak it closes.
- `odoo-ai-agents` - the evidence-lifecycle contract named an owning file for each of its seventeen
  cleanup sweeps; two of those files contained no sweep. Both are now written at their owner sites,
  the table agrees with reality again, and a guard asserts that agreement so a row cannot claim
  coverage that does not exist.
- `odoo-ai-agents` - lint-class gates were removed from the coder agents but continued to gate every
  wave through instance provisioning, which unioned them into any test run. Provisioning now takes an
  explicit gate role, refuses rather than guesses when it is absent, and resolves to per-module
  verification at the front door, so an unstated caller can never drift back toward installing lint.

Also fixed:

- `odoo-ai-agents` - forward-port wrote one intent record per commit under a run-level slug, so a
  commit touching two modules had both modules' workers writing the same path with no owner and no
  merge rule. Records are now namespaced per module. The extractor's own slug fallback, which
  silently reconstructed the unsafe shape whenever a caller omitted the field, is gone: the field is
  required and its absence is refused.
- `odoo-ai-agents` - a failed forward-port module pass had no legal retry outside the resume-capable
  handoff tier, because a fresh dispatch was banned outright. The other tiers now have a named,
  non-concurrent superseding path.
- `odoo-ai-agents` - a dispatch brief could satisfy its own self-check while dropping the survey
  findings a human had handed over, because the survey pointer was named nowhere in the brief
  skeleton. It is registered now and verified by the coder-family self-checks. The caller identity
  field was classified as always-required in one file and as conditional in another; the
  contradiction is resolved, and five concrete dispatch templates that omitted it carry it.
- `odoo-ai-agents` - the four read-only analyst agents that returned in an ad hoc format now carry the
  same always-on completion report and the same ban on an unqualified "waiting" as every other agent.
- `odoo-ai-agents` - the recon tier rule and the scouting-persistence contract reached only a fraction
  of the sites they govern: one guard matched four of eighteen dispatch sites, another was a
  hardcoded file allowlist, and recon performed by invoking a leaf skill directly had no tier lever at
  all. The allowlist is replaced by a whole-tree structural scan, the two detectors share one verb
  alternation so phrasing cannot exempt a site from registration, and the leaf-skill path has a stated
  rule. A debug scout whose findings were persisted nowhere now writes them where a resumed session
  can read them back.
- `odoo-ai-agents` - `allocator.py` leaked a lease when a subcommand was invoked with the single-dash
  help flag; help is now intercepted before argument parsing for every subcommand and every spelling
  the parser accepts.
- `odoo-ai-agents` - five cross-references described the documentation language resolver by a tier
  count it no longer has, pointing readers at a tier that was removed precisely because it hardcoded a
  default locale. A guard now checks that a cited count agrees with its target heading. Self-referential
  tracker citations are out of the shipped tree, and the one hook whose file mode differed from its
  twelve siblings matches them.

## [4.20.0] - 2026-08-03

### Added

- `odoo-ai-agents` - the dispatch handoff contract is now binding on both sides. A brief is invalid
  without the paths to the design, the plan and the survey findings the callee needs, and without the
  caller's own return identity; `snippets/dispatch-brief.md` gains that field and the brief
  self-check verifies it. On finishing, an agent emits a three-part completion report, and an
  unqualified "waiting" is a forbidden outcome - an agent that must wait names what it waits on, who
  can unblock it, and what the caller does next. Previously a callee that finished had no addressee
  and could wait indefinitely, stalling every actor upstream that assumed work was still running.
  The existing work-ethos principles are CITED at the dispatch sites rather than restated.
- `odoo-ai-agents` - `snippets/git-delegation.md` § Base-branch resolution: a decidable algorithm
  that resolves a new worktree or branch's base from the version-named series branch, keyed off the
  run header's Odoo version, with a stated action for zero matches, several matches, a local branch
  behind its remote, a detached HEAD and a dirty tree. The domain-agnostic half - an explicit start
  point is mandatory for `worktree add`, `checkout -b`, `switch -c` and `branch`, because omitting it
  silently resolves to HEAD - lives once in `git-toolkit`'s safety contract and is pointed at, never
  restated.
- `odoo-ai-agents` - `scripts/lib/allocator.py reap-orphans`: a database-side sweep for the class the
  existing reclaim path cannot reach, an ephemeral-shaped database that no lease references at all.
  Its ownership predicate fails CLOSED on every axis (an unreachable cluster is skipped rather than
  assumed empty, an unmeasurable age is not assumed old enough, any leased name is left to the
  existing path), and the default is list-only - dropping requires an explicit opt-in.
- `odoo-ai-agents` - `skills/odoo-demo-recording` narrated evidence mode: per-step captions, a
  before/after badge and a verdict end-card, so a bug-evidence clip explains itself without a live
  narrator. Only capabilities verified against the recorders' real tool schemas are used; a recorder
  family that cannot inject script is excluded by name, and a missing frame assembler degrades to a
  stated non-fatal status instead of promising an output the tool surface cannot produce.
- `odoo-ai-agents` - `skills/odoo-forward-port` groups by MODULE first and by commit second within
  each module, with at most ONE worker per module across a run, named once and resumed by name for
  every later commit rather than re-dispatched cold. Determining intent commit by commit meant a
  module's commits were spread over as many workers as it had commits and no worker ever saw the
  module whole - a revert pair or two commits editing one file could land in different contexts.
  A view-topology check is added to the same pipeline so a re-implement never leaves an
  unconditional same-module inherit view stacked on the base view it could merge into.

### Fixed

- `odoo-ai-agents` - `allocator.py acquire` now REFUSES (exit 5) instead of silently defaulting the
  addons path to the catalog's principal checkout when the caller's cwd is a linked worktree of the
  same repository. It fingerprints the shape by git-common-dir (identical across a repo's worktrees)
  against `--show-toplevel` (per checkout). Every earlier round fixed a call path and left the
  DEFAULT guessing, with prose covering the gap - and prose does not refuse, so a build could load
  the principal checkout while reporting a green result for code it never compiled.
- `odoo-ai-agents` - a lease is now OWNED: `acquire` persists the caller's run id onto the lease row
  instead of only echoing it back. `assert-droppable` prints its refusal reason to stderr, a refused
  drop exits non-zero rather than reporting success, and `acquire --help` can no longer reserve a
  lease as a side effect of argument parsing.
- `odoo-ai-agents` - a recon or scouting dispatch that states no model tier inherits the CALLING
  context's model, which is why the highest-traffic recon phase ran at the caller's tier. Recon now
  states its tier explicitly, and `skills/_shared/concurrency-guard.md` records the inheritance
  mechanism itself so the rule applies at sites nobody has authored yet. Separately, every scout's
  findings are persisted PER AGENT and read back by a later phase; a parent-authored aggregate is a
  summary from the parent's own context, which is the caller-memory dependency the contract exists
  to remove. `snippets/scouting-persistence-contract.md` owns the consumer registry, and the guard
  fails when a recon site is unregistered rather than only when a known site regresses.
- `odoo-ai-agents` - `skills/run-harness` contradicted itself: one section mandated auto-advance with
  a closed exception list while another permitted stopping at any time, so pausing at every wave
  boundary was compliant with the text. The advance rule now lives in one place with four enumerated
  stop conditions, and `docs/reference/workflow-harness.md` points at it instead of restating a
  competing unbounded version. The underlying fact that hooks cannot coerce the main agent is kept;
  what is removed is the open-ended permission built on top of it.
- `odoo-ai-agents` - lint-class execution (`test_lint`, `test_pylint`, pylint-odoo, eslint, flake8,
  ruff, prettier) moves out of per-module and per-wave work into ONE pre-PR step, ordered after the
  i18n reconcile and the acceptance run so both land before the PR. Acceptance was previously wired
  to fire AFTER the PR was opened, and the i18n reconcile was absent from the drive-to-done loop
  entirely, so a run driven by the harness skipped translation. Static checks that are not
  CI-parity lint gates stay where they are.
- `odoo-ai-agents` - no hardcoded locale default remains. The defect spanned three layers: prose, the
  setup step that seeded the language registry, and two tests that asserted the hardcoded value MUST
  be present - so every previous attempt to fix it turned a test red and was reverted, with CI green
  throughout. The target language is now a required input with no built-in default, and its absence
  returns a needs-context outcome rather than a guess.
- `odoo-ai-agents` - agent-facing prose no longer points at things that do not resolve: a manifest
  filename written without its surrounding double underscores (no Odoo module contains that file),
  and an in-repo documentation path that resolves nowhere. Both are corrected at every occurrence
  rather than only where they were reported, and a guard scans the whole tree for the class.

## [4.19.0] - 2026-07-31

### Added

- `odoo-ai-agents` - `scripts/lib/resolve_project_dir.sh` and `scripts/lib/paths.py` accept an
  optional explicit root (`--root <abs-path>` on the CLI, a positional argument when sourced,
  `root=` in Python). Omitting it is byte-identical to the previous cwd-based behaviour. This removes
  the `cd`-wrapper fragility class for cross-worktree dispatch.
- `odoo-ai-agents` - new `snippets/scouting-persistence-contract.md`: a scouting phase writes its
  findings to a tier-correct file and the consuming phase READS them back, with a resume rule that
  skips a re-dispatch when a fresh artifact for the slug exists. Wired into intake Phase R and
  Phase 0, forward-port P0/P1, the code-review and doc-illustration scopers, and the rebase intake.
  Previously each of these produced findings that lived only in the orchestrator's context, so a
  resumed run re-scouted from zero.
- `odoo-ai-agents` - new `snippets/upg-conventions.md` § Convention 0: a major-series module upgrade
  is a CODE upgrade. It states the P4-time dispositions (no old-series compatibility, no migration
  script, no version bump; implement a recorded `reuse_candidates[]` target-core mechanism instead of
  a shim; a decidable vendor-currency trigger with an explicit cap AND an action rule). Both coder
  agents gain a one-line, byte-identical pointer naming their triggering brief, so a coder can no
  longer inherit only forward-port's opposite disposition.

### Fixed

- `odoo-ai-agents` - the addons_path separator (comma, matching Odoo's own `--addons-path`/
  `addons_path` syntax) now has a single source of truth: `scripts/lib/instances_io.py`'s
  `join_addons_path`/`split_addons_path` (Python) and `scripts/lib/resolve_instances.sh`'s
  `_addons_path_to_array` (bash). Every producer (`instances_io.py`, `allocator.py`) and shell
  consumer (`45-venv.sh`, `47-instance-reset.sh`, `50-instance-spinup.sh`, `55-instance-ops.sh`,
  `05-prereq-check.sh`) now goes through one of the two homes instead of hand-rolling a join/split,
  closing two live producer/consumer separator mismatches that only fire with a 2+-entry
  addons_path: `50-instance-spinup.sh`'s odoo-bin scan (setup path) and `55-instance-ops.sh`'s
  odoo-bin scan (the path every module init/update/test call goes through). A structural test
  (`test_addons_path_no_hardcoded_separator.py`) now fails on any new hardcoded separator outside
  the two SSOT homes, and a cross-language parity test proves the Python and bash sides agree on
  the same round trip.
- `odoo-ai-agents` - a per-module verification instance now loads the worktree the code was written
  in. `scripts/lib/allocator.py acquire` gains `--addons-path-override`, `odoo-instance` gains a
  `WORKTREE_PATH` input with a mechanical re-rooting rule, and the instance-handle contract gains a
  narrowly-worded worktree-addons carve-out plus a single addons-coverage assertion every consumer
  points at. Previously the instance loaded the CATALOG addons list (the principal checkout), so a
  per-module test could pass against code the instance never loaded. Also: the allocator now rejects
  an unknown flag instead of silently ignoring it, and a missing instance catalog produces a named
  diagnostic pointing at `/odoo-setup` instead of a silently-wrong project-local path.
- `odoo-ai-agents` - `snippets/state-root-resolution.md` gains ISOLATE rows for
  `recon/<slug>-<date>/` and `visual/current/<slug>/`, drops the visual-regression comparison set from
  the reusable-across-runs bucket (it is per-run by construction), and documents the resolver's new
  explicit-root form. A new guard asserts both rows land in the ISOLATE table, not the SHARE one.
- `odoo-ai-agents` - `odoo-visual-regression`'s state-B comparison set moves from the SHARE tier to
  per-run ISOLATE (`<ISOLATE_DIR>/visual/current/<slug>/`) and is deleted after the Round-4 verdict is
  recorded. Two concurrent runs comparing different builds previously wrote the same screenshot paths
  in a cross-run directory. Baselines stay SHARE (they are reused across runs). The legacy-state
  migration now dispatches `visual/baselines/`'s own children so a nested legacy `current/` is
  discarded with a printed line instead of riding into SHARE - the first `visual/` case that migration
  helper has ever had a test for.
- `odoo-ai-agents` - `upg-triage-table.md` no longer lists "a single manifest version bump" as an
  ADAPT scenario; three other files forbid what it permitted.
- `odoo-ai-agents` - wave topology gains a fifth value, `single`, declared at its one owner
  (`run-harness/references/wave-integration.md`). A wave that dispatches `n <= 1` modules now
  dispatches directly into the integration worktree instead of forking, cherry-picking and converging
  a child worktree for a single module. For `n >= 2` the child worktree is retained for
  poison-containment. An absent `topology` field still takes the fan-out path. A new guard asserts the
  value set has exactly one definer - three files previously restated it.
- `odoo-ai-agents` - fixed a stale count word left behind by the `single` topology value above:
  `wave-integration.md` (the enum owner) and `run-harness/SKILL.md` both said "the four topologies"
  right next to a five-value enumeration, an ambiguity a reader could not resolve (stale prose, or a
  deliberate exclusion, and if so, which value). Both now say explicitly that four of the five values
  describe multi-module ordering and `single` collapses the wave with no ordering to describe. A new
  guard computes the enumerated value count and asserts every count-word reference to
  "topolog(y|ies)" in either file agrees with it (or with count-1 when scoped to "multi-module"), so
  a future sixth value reddens this test instead of leaving a silent inconsistency.
- `odoo-ai-agents` - the OSM session pin is scoped per MCP session, so `odoo_version='auto'` can
  resolve to another actor's version if one shares that session. The ban is now enforced
  structurally: a new value-identity assertion
  rejects the sentinel in every example call, 43 instruction sites now pass a concrete-version
  placeholder, the guard's own docstring and failure messages no longer prescribe `'auto'`, three
  lexical evasions it demonstrably missed are covered, and the rule is extended to
  `set_active_profile` (whose surface description carried no concurrency warning at all). The four
  sites that quote the sentinel in order to forbid it are asserted to keep doing so.
- `odoo-ai-agents` - `docs/personas/dev.md` and `dev.vi.md` had drifted from the generated tool
  surface: the `test_base_classes` row dropped `SavepointCase` and "for the given version" (the clause
  that stops an agent recommending a base class on a series where it no longer exists), and the
  `test_coverage_audit` row dropped the whole-module framing and the "static reference coverage only,
  not runtime executed" caveat. All four cells are corrected, and a new guard
  (`tests/test_persona_docs_consistency.py`) computes the required identifiers and safety clauses from
  `generator/server-surface.json` so the mirrors cannot drift again, plus a Vietnamese-language guard
  against reintroducing the "pin once, then omit `odoo_version`" claim in a table row. The persona
  tables stay hand-maintained by design; translation wording is explicitly out of the guard's scope.
- `odoo-ai-agents` - `docs/personas/dev.md` and `dev.vi.md` each taught the exact pattern the OSM
  session-pin rule forbids, in a worked example rather than a table row: "no need to repeat the
  version on follow-up calls" / "khong can lap lai phien ban o cac loi goi tiep theo". A live example
  contradicting the rule stated one section earlier is the most persuasive kind of wrong prose, so
  both are rewritten to require the concrete version on every call. The same defect, in a different
  wording, was also found and fixed in `snippets/gemini-gem-instructions.md`'s hand-written bootstrap
  paragraph ("...instead of repeating it"). The persona-docs guard is widened from table rows to the
  whole file in both languages (a table row was only one syntactic shape prose can take, and scoping
  the earlier guard to that one shape is exactly how this evasion survived); the English-language
  evasion guard in `tests/test_agent_facing_guidance.py` gains a matching "repeat...version" pattern,
  since it already scans skills/snippets/agents/docs and is this repo's single home for English-only
  evasion detection - the Vietnamese counterpart stays in the persona-docs guard, so the rule is not
  duplicated across two files.
- `odoo-ai-agents` - `installable` is now resolved from the target clean-tip `__manifest__.py`
  everywhere, not from OSM. The Odoo Semantic index does not carry the manifest flag, but
  `module_inspect` SUCCEEDS, so the documented "OSM MISS" fallback branch never fired and the
  forward-port pipeline could classify a module against a value OSM never supplied. The prober's
  `manifest_path` becomes a REQUIRED orchestrator-produced input (a leaf cannot read a file at a ref
  under the bounded-read allowlist), its absence is a BLOCK rather than an `ungrounded` verdict, and
  the same inversion lands in forward-port's P2/P8/model-triage prose, both triage-table
  short-circuit gates, two snippets, the feature cataloger, the tool registry and the README. The
  prober's now-unreachable `UNKNOWN` target-state and `(tentative)` verdict branches are removed
  (the manifest read always resolves `True`/`False`/absent-key-as-`True`/absent-file-as-`ABSENT`, or
  BLOCKS - there is no remaining ambiguous case). The durable, cross-agent-readable field is
  `installable_false=yes|no`, written to `merge-log.md` by BOTH the orchestrator's direct
  resolution (categories 1-2) and the prober's verdict (category 3); the prober's internal
  `target_installable`/`target_grounding` values are never persisted and no other file parses them.
- `odoo-ai-agents` - `odoo-i18n` and `odoo-translator` now carry `WORKTREE_PATH`. `.po`/`.pot` files
  are git-tracked and `odoo-translator` is a separate agent context that does not inherit the caller's
  cwd, so a translation write previously landed in whatever checkout was ambient. The i18n recipe's
  "export against the adapted code" requirement now names its MECHANISM (pass `WORKTREE_PATH` through
  to `odoo-instance`, which re-roots the addons list via the existing `--addons-path-override`) plus a
  pointer to the addons-coverage assertion - without them the non-destructive diff-review had nothing
  to adjudicate and a worktree-only msgid was lost unseen. Also fixed: `odoo-translator.md` told the
  leaf to validate via `polib`, a library the rest of that same file (and several other places in the
  plugin) forbids and that is not in `requirements.txt` - a leaf told to use an absent library
  improvises. A new structural test (`test_git_tracked_writers_carry_worktree_path`) asserts every
  agent/skill that names a git-tracked write target in its frontmatter carries `WORKTREE_PATH`,
  against a shrink-only known-red allowlist.
- `odoo-ai-agents` - `odoo-i18n` P0's approval STOP is now foldable: when a caller dispatches it as a
  required step and supplies explicit target languages, an instance handle (or a worktree-addons
  self-provision), and a worktree, P0 returns its scope summary for the caller's own gate instead of
  opening a second human stop per invocation. Inside such an invocation the tier-5 `["vi_VN"]`
  language default is unreachable - it records `i18n: not-applicable` instead, so a mandated pass can
  never silently generate Vietnamese catalogs for a user who did not ask.
- `odoo-ai-agents` - the i18n reconcile is now MANDATORY, with an enumerated escape, declared ONCE in
  a new `snippets/i18n-mandate-contract.md` that both callers point at. `odoo-modules-upgrade` P5.7
  runs it for every SURVIVING module (KEEP / REWRITE / MERGE / SPLIT / RECONCILE) - only
  DELETE-absorbed and OBSOLETE skip - instead of auto-skipping when a content diff found no
  translatable token: the `.pot`/`.po` tooling changes across a major series regardless of whether a
  module's own strings did. `odoo-forward-port` splits the decision from the dispatch: 8e now
  COMPUTES and records two decidable conditions on the module's `merge-log.md` row (an 8-signal
  trigger over the already-materialized commit dumps, biased toward a HIT since a false negative
  ships a broken catalog and a false positive only costs one no-op reconcile; and
  `installable_false == no`, the same field forward-port's manifest-grounding fix already
  standardized on), and a new P9.5 DISPATCHES `odoo-i18n` after the P9 instance exists - 8e used to
  dispatch inline before any instance existed, risking a redundant second provision since `odoo-i18n`
  hard-BLOCKs without one. Six enumerated escapes, each recorded in `install-test.md` /
  `merge-log.md`, none silent. The mandate is NOT provisioning-free: each reconcile pass needs a
  fresh DB even when the P5/P9 server lease is reused.
- `odoo-ai-agents` - the plugin README's forward-port pipeline diagram and phase table now document
  the new P9.5 i18n-reconcile phase, and the P8/8e wording is corrected to match (8e COMPUTES the
  `i18n_due` signal; the `odoo-i18n` dispatch itself happens at P9.5) - the same earlier commit that
  added P9.5 to SKILL.md correctly updated the sibling modules-upgrade pipeline's README section but
  left forward-port's stale. A separate, older "12-phase" vs "13-phase" phase-count inconsistency
  in the README's top-of-file summary, found during the same sweep, is also reconciled. A new test,
  `tests/test_readme_phase_parity.py`, extracts each pipeline's phase anchors straight from its
  SKILL.md and asserts the README's matching section (both the mermaid diagram and the phase table)
  documents exactly that same set, so this class of drift cannot recur silently.
- `odoo-ai-agents` - `concurrency-guard.md`'s OSM pin-race section is renamed "OSM session-pin
  race" (covering both `set_active_version` and `set_active_profile`, per an earlier widening).
  Nine pointers left dangling by that earlier rename (a mix of quoted-no-keyword, bare-no-`.md`,
  and reversed-word-order phrasings, one of them in `docs/` where the old guard never looked) are
  corrected to the current name, along with two local section headings that had drifted to a
  stale term. The pointer guard in `tests/test_agent_facing_guidance.py` recognised only one
  syntactic shape and skipped `docs/` entirely - both defects are why the nine survived unnoticed.
  It now scans every markdown file in the plugin and recognises a stale reference regardless of
  phrasing or filename proximity, and reads the heading text dynamically so a future rename
  cannot silently leave pointers behind again.
- `odoo-ai-agents` - the same section's scope claim was itself wrong: it said the
  `set_active_version` / `set_active_profile` pins are scoped to the API key alone, so two
  independent sessions sharing a key would clobber each other - the server actually shares each
  pin per `(api_key_id, mcp_session_id)`, i.e. per MCP session; two independent sessions never
  interfere, and the real hazard is multiple actors (a parent plus any subagent it dispatches)
  sharing ONE session, confirmed empirically. Corrected the claim, reworded the `'auto'` ban's
  rationale to the decidable one (an agent can never prove at call time that it is its session's
  only actor), stated plainly that the ban is a policy stricter than the server's own contract
  (the server itself permits a single-actor session to reuse `'auto'` per ADR-0029), and noted the
  `set_active_profile` clobber is authz-safe (narrowing-only, fail-closed - it can only narrow a
  view, never widen or leak). `generator/server-surface.json`'s descriptions for both tools are
  corrected to state the same per-session scope (first sentence unchanged, so `make gen` produces
  no diff), and a new test binds the section's scope claim to that SSOT so the two cannot drift
  apart again.
- `odoo-ai-agents` - the instance-identity attach guard's `_identity_token` (`50-instance-spinup.sh`)
  hashed its addons_path argument RAW: the same PR's `instances_io.py` `_emit` unification from
  colon- to comma-joined addons_path (see above) silently changed every recorded token's input
  format too, so a machine that had already spun up an instance under the pre-upgrade checkout would
  see a false `COLLISION` on its next "already up" check for a real, unchanged, 2+-entry addons_path.
  `_identity_token` now canonicalizes its input (via `resolve_instances.sh`'s
  `_addons_path_to_array`) before hashing, so the same real addons_path always hashes to the same
  token regardless of which separator produced the string - this class of regression cannot recur. A
  new `_identity_token_legacy` reproduces the pre-fix raw-hash behavior, and `_identity_ok` now
  accepts either token, so a marker already on disk from before this fix is still recognised as the
  same instance instead of a false collision.
- `odoo-ai-agents` - `upg-phase-detail.md`'s P0 step (2) `profile_inspect` call referenced
  `<target_version>`, a variable step (4) - several steps later - is the first to bind; the earlier
  'auto'-sentinel-ban sweep mechanically substituted every `odoo_version='auto'` with a
  concrete-version placeholder without checking whether that variable was actually in scope at each
  call site. Fixed to reference `<inferred_series>`, the series step (1) already binds one line
  above. Every other placeholder the sweep introduced (44 occurrences across 14 files) was checked
  and confirmed resolvable at its point of use.
- `odoo-ai-agents` - the `SELF_PROVISION: worktree-addons` per-module worktree-addons carve-out field
  is load-bearing in `odoo-coder.md`'s own dispatch logic but was undeclared in
  `snippets/dispatch-brief.md` (the caller-side dispatch-brief SSOT) and unvalidated by
  `odoo-coder.md`'s own `## Brief self-check` (copied from that SSOT's SPAWNER template) - a caller
  reading only the SSOT would not know to emit the field, and a brief malformed by carrying both
  `INSTANCE_HANDLE` and `SELF_PROVISION: worktree-addons` would silently take the wrong branch
  instead of being caught. Both the SSOT and `odoo-coder.md` now declare/validate the field with the
  identical token.
- `odoo-ai-agents` - Convention 0 (`snippets/upg-conventions.md`) was declared but never actually
  reachable at the moment a real P4 dispatch fires: the only pointer to it lived in `SKILL.md`'s
  P2-phase aside, two phases upstream of the concrete `upg-phase-detail.md` P4 dispatch-brief
  template a coder actually receives, so a brief built strictly from that template never named the
  convention or the coder-disposition marker string (`upg-conventions.md`) the backend/frontend
  coder's own selector keys on - Convention 0(c)'s vendor-currency bias could never fire. The file's
  own gating banner also blanket-gated "the rules below" to Viindoo Standard/Internal profiles while
  a later line claimed Conv-0/3/4 were core and reachable via a "version INDEX By-task table" that
  does not carry Convention 0 for any profile. Fixed: the P4 brief template now cites Convention 0
  by literal path (satisfying both the citation and the disposition-selector marker in one field)
  and wires its vendor-currency pass as an actionable instruction step; the gating banner now scopes
  the Viindoo-only gate to Conventions 1-2 explicitly and states the real, already-unconditional
  reachability route for Convention 0 instead of the dead INDEX-table claim. Also fixed: P5's
  create-instance dispatch never named the addons path P5.7 depends on ("its addons path MUST cover
  WORKTREE_PATH") - it now passes `WORKTREE_PATH: <path>/upg-integration`, reusing the existing
  `odoo-instance` WORKTREE_PATH field and its `--addons-path-override` substitution mechanism (no
  second, bespoke mechanism introduced).
- `odoo-ai-agents` - a second PR #189 runtime review found the i18n mandate self-contradictory and
  two of its escapes unusable, plus a forward-port verify phase that could go GREEN against
  un-adapted code. `snippets/i18n-mandate-contract.md` (escape E3: "record + proceed") and
  `skills/odoo-i18n/SKILL.md`'s own gate ("any of three inputs missing, incl. TARGET LANGUAGES,
  falls back to a standalone STOP") gave opposite instructions for the same no-language case, and
  the SAME skill's own P0 tier text separately said the caller "MUST pass explicit TARGET
  LANGUAGES" - self-contradictory on top of the cross-file one. Resolved in one direction: a
  MANDATED invocation never opens a fresh interactive STOP for ANY reason. Missing WORKTREE_PATH or
  INSTANCE_HANDLE/SELF_PROVISION (the two hard preconditions) is a caller-contract violation that
  returns `status: BLOCKED` to the caller's own gate; TARGET LANGUAGES is best-effort only -
  `odoo-i18n`'s own P0 tiers 2-4 (registry / `.po`-filename inference / live instance query) still
  run against whatever the caller could NOT supply, and only once all four tiers are empty does
  escape E3 fire (record + proceed, translate nothing, never stop) - closing both the deadlock risk
  and the "silently skip a resolvable language" risk. Escape E2 ("no `i18n/` dir + zero
  translatable-delta signals") was unreachable for `odoo-modules-upgrade` because its only trigger
  table was headed "forward-port condition 1 only" and read a forward-port-only artifact path; the
  table now names a modules-upgrade scan target too (the module's own P4 adapt diff), and a new
  "Catalog-presence check" section defines - ONCE, mechanically - what "ships no `i18n/` directory"
  means (a `WORKTREE_PATH` disk read, never OSM, which does not index `.po`/`.pot` at all) so both
  flows evaluate E2 identically instead of guessing. Forward-port's P9 (RED-then-GREEN verify) named
  `WORKTREE_PATH` nowhere in the whole skill - only P9.5 (i18n) did, on the unbacked assumption that
  P9's instance already covered it - so P9 could go GREEN against the principal checkout instead of
  the adapted `fp-integration` worktree with no error raised (the SAME defect class `3d9928e`
  already fixed for `odoo-git-rebase`/`odoo-coding`/`odoo-coder`/`worker-brief`; forward-port was
  simply absent from that commit). P9 now passes `WORKTREE_PATH: <path>/fp-integration` to
  `odoo-instance` and re-roots the addons path before any verify command, making P9.5's addons-path
  claim - and the i18n mandate's stated dependency on it - actually true; this also closes a
  regression-hunt DEGRADES where P9.5 could reintroduce a per-invocation STOP for a module gaining
  its first-ever translatable string (zero source-side `.po` files to infer a language from) - it
  now omits TARGET LANGUAGES in that case and defers to `odoo-i18n`'s own tiers/E3. Finally,
  `fp-triage-table.md` Table 1's P0 short-circuit gate instructed reading a `manifest_path`
  described as "the value P2 resolved" - P2 runs strictly after P0, so this was unexecutable at the
  point it governs (confirmed via `git show ca80dce`, which replaced a self-contained, P0-executable
  check with this forward reference). Table 1 now cites the disk-read Discriminator
  `fp-installable-false.md` already defines, executable at P0 with no OSM claim; Table 2 (which
  governs P8, after P2) is untouched. 23 new tests across `tests/test_i18n_mandate_reconciliation.py`
  (new) and `tests/test_forward_port_hardening.py`, each proven red against the pre-fix text.
- `odoo-ai-agents` - a third PR #189 runtime review found that earlier fixes in this same PR left
  surviving siblings of the exact claims they removed, in files the fixing commits never touched,
  because three of the PR's own guard tests were scoped to the shape of the instance just fixed
  rather than the whole claim class. The "worktree already carries the dependency, so cross-wave
  addons-path resolution is structurally solved/impossible" conflation - the same one `3d9928e`
  rewrote out of `wave-integration.md` Example 3 - survived in `snippets/module-coordination-ledger.md`
  (both its scope note and decision-table case 4), `skills/run-harness/SKILL.md`'s own
  fork-module-worktrees step, and `skills/odoo-intake/references/plan-mode-schema.md`'s Block 2W edge
  description; all four sites now state the corrected relationship (the worktree CONTAINS the
  dependency's source by git-fork construction, but reaching the addons-path is a POLICY step -
  `WORKTREE_PATH` + `SELF_PROVISION: worktree-addons`, set by `odoo-coding` on every such dispatch -
  not a structural guarantee of the fork itself). `agents/odoo-doc-scoper.md`'s Hard-constraints
  section still framed `module_inspect`/`describe_module` as a usable fallback for an "ambiguous"
  `installable` state, a case Step 2's disk-read rule (two paragraphs earlier in the same file) never
  leaves open - the same OSM-does-not-carry-`installable` fact this PR established elsewhere
  (`ca80dce`), phrased differently enough to survive that commit's full-repo grep.
  `skills/odoo-intake/references/maintainers.md` still said "the 4 wave-batch topologies" after the
  enum grew to 5. `snippets/test-execution-handoff.md` and `agents/odoo-backend-coder.md` (two sites)
  still stated the pre-carve-out absolute ("a forwarded `INSTANCE_HANDLE` always wins, full stop")
  with no mention of the `SELF_PROVISION: worktree-addons` carve-out `test-execution-handoff.md`'s own
  named consumer `odoo-coder`/`odoo-backend-coder` is authorized to use, and
  `odoo-backend-coder.md`'s bounded `/test_lint` self-provision recipe omitted `WORKTREE_PATH` - the
  same worktree-correctness defect class `3d9928e` fixed at the sibling `odoo-coder.md` call site,
  left open here (net zero line delta on this always-loaded file: both edits lengthen existing lines,
  add none). Three guards are widened from the exact shape they were scoped to, to the whole class:
  the addons-path-structurally-solved guard now scans every file in the plugin for a 5-pattern family
  (was: one literal phrase in one file; pre-fix finding count against the whole tree: 5, across the 3
  files above); the OSM-resolves-`installable` guard now scans every markdown file in the plugin for a
  bare tool-name mention (not just call syntax) co-occurring with `installable` outside an explicit
  negation, chunked by markdown block/fence/sentence boundary to avoid both known false-positive
  shapes (was: forward-port files only, call-syntax only; pre-fix count: 1); the topology count-word
  guard now scans the whole plugin and accepts a digit token with up to 3 filler words before
  "topolog" (was: two hardcoded files, spelled-out number words only; pre-fix count: 1). 4 new/widened
  guard tests added, each proven red against the pre-fix text before being fixed green.
- `odoo-ai-agents` - a fourth PR #189 runtime review found the batch's remaining fixed-but-wrong
  claims. `odoo-visual-regression/SKILL.md`'s standalone `<slug>` derivation had no anti-collision
  component - two concurrent runs sharing the identical comparison intent still derived the
  identical slug and collided on `<ISOLATE_DIR>/visual/current/<slug>/`, the exact collision the
  PR's `702dabf` claimed to have closed. It now mints
  `<intent-slug>-<YYYYMMDD>-<4 random chars>`, reusing the SAME suffix mechanism
  `odoo-intake/references/phase-p-run-dag.md:43` already uses for its run id, rather than inventing a
  second one; the sibling `visual/qa/<slug>/`, `visual/debug/<slug>/`, and `visual/screenshots/<slug>/`
  subpaths share the same underlying weakness (no anti-collision suffix in their own slug generation)
  but are NOT fixed here - their own "generate one slug" instructions have no derivation algorithm at
  all to extend with a matching one-line suffix, so they are recorded, not patched, in this change.
  The comparison-set retention rule fired only "after the Round-4 verdict is recorded," leaking a
  failed/abandoned/interrupted run's directory forever; it now triggers before ANY terminal status
  (DONE/BLOCKED/NEEDS_CONTEXT/NEEDS_NEXT alike), backstopped by a 24h-TTL orphan sweep the next run
  performs at its own Round 0 for the crash case no terminal-status prose can reach. The
  `scouting-persistence-contract.md` staleness check told the reader to compare against "the
  recorded target ref," but the four-field `findings.md` schema it names had no ref field at all -
  the branch was unexecutable; the schema now carries a `target_ref:` header line (outside the
  capped finding-line count, so the declared 20-line/200-char cap is unaffected), and
  `odoo-intake/SKILL.md`'s writer and reader both name it. `odoo-modules-upgrade`'s Convention 0(c)
  told the agent to record a `vendor_api_checked:` value with one of six enumerated forms, but no
  P2/P4/P5 output schema reserved a field for it; `absorption/<module>.md`'s P2 output FORMAT now
  reserves the slot, and the P4 dispatch brief's step 0c (the actual write instruction) names the
  same field and file. Verified `agents/odoo-coder.md`'s "Brief self-check" already validates
  `SELF_PROVISION: worktree-addons` (landed earlier in this PR, `52225ad`) - no further action needed
  there. 14 new/widened guard tests added across 3 files (1 new file), each proven red against the
  pre-fix text (via a targeted stash of the source-only edits) before being fixed green.
- `odoo-ai-agents` - a fifth PR #189 runtime review (a read-only role-play as the executing
  run-harness agent) found three more pre-existing runtime-contract gaps in the between-wave
  integration loop. (1) The saga rollback (`skills/_shared/integration-loop.md`) was a literal
  `git reset --hard` of the run-integration branch - one of git-toolkit's 8 destructive
  human-confirm-gated ops - while `run-harness/SKILL.md` bills the entire between-wave advance as
  autonomous L1 drive-to-done with "NO per-wave stop" and no carve-out for the rollback, so a real
  mid-wave failure would BLOCK unexpectedly on a run the agent was told never stops. The rollback is
  now a worktree ABANDON + RE-FORK at the anchor SHA (never a live-tree `reset --hard`), with the
  reasoning stated inline: run-integration is a disposable, never-pushed, run-scoped branch, so
  nothing unique is discarded (the anchor SHA and every module's own commits stay reachable off
  their own branch) - the rollback therefore fires no destructive-confirm gate by construction, not
  by exemption, keeping the between-wave advance genuinely autonomous. No `git-toolkit/**` file was
  touched. (2) `wave-integration.md`'s `independent` topology was labeled "(all parallel)" /
  "Maximum parallelism", but the between-wave loop it describes dispatches modules SEQUENTIALLY (one
  blocking `Skill("odoo-coding", ...)` call at a time) - an identical "built in parallel" claim was
  also found in `plan-mode-schema.md`'s Block 2 template and worked example (a differently-shaped
  sibling of the same defect). Both are fixed: the label now states plainly what `independent` DOES
  mean (module build ORDER is unconstrained) versus what it does NOT mean (concurrent dispatch -
  only the intra-module work-item fan-out inside `odoo-coder` is real concurrency). (3)
  `topology: single`'s "already-provisioned JOB-tier integration worktree" was never created by a
  named step - `run-harness/SKILL.md`'s "Run start" only forked a branch, unlike sibling skills
  (`odoo-modules-upgrade`, `odoo-forward-port`) which each spell out an explicit
  "Create the JOB-tier integration worktree: invoke the `git-toolkit:git-ops` skill ... to add a
  worktree" step; Run start now carries the same explicit step, and `wave-integration.md` § Single
  points back at it. 11 new guard tests added (1 new file), each proven red against the pre-fix text
  (via a targeted stash of the source-only edits) before being fixed green.
- `odoo-ai-agents` - three more pre-existing runtime-contract gaps closed. (1) The run-scoped
  `visual/qa/<slug>/`, `visual/debug/<slug>/`, and `visual/screenshots/<slug>/` sibling subpaths
  (unlike `visual/current/<slug>/`, fixed earlier in this PR) had no collision-proof slug-derivation
  rule - `odoo-ui-review` had no slug instruction at all - so two concurrent same-intent runs could
  mint the identical slug and overwrite each other's evidence. New
  `snippets/visual-evidence-lifecycle-contract.md` states the
  `<intent-slug>-<YYYYMMDD>-<4 random chars>` derivation once (the same mechanism
  `phase-p-run-dag.md:43` and `odoo-visual-regression` already use); `odoo-acceptance`, `odoo-debug`,
  and `odoo-ui-review` (plus `odoo-ui-reviewer`) now cite it instead of restating or omitting the
  rule. (2) `ui-debug-session.workflow.yaml` promised each phase writes state so a multi-hour
  session can resume, but the `inspect` phase diagnosed from conversation context and never read
  back the `collect-symptom`/`reproduce` phases' own persisted artifacts - a session resumed in a
  fresh context would silently diagnose from nothing. `collect-symptom` now names its artifact
  explicitly (`.odoo-ai/debug/<slug>-symptom.md`) and `inspect`'s `nl_trigger` now instructs an
  explicit read-back of both prior artifacts from disk before diagnosing, making the resume promise
  true. (3) Neither state tier had any garbage collection - `visual/qa/`, `visual/debug/`, and
  `visual/screenshots/` evidence is deliberately RETAINED past its own run (it is the cited evidence
  behind a verdict/diagnosis/review) but nothing ever swept it, leaking one directory per run
  forever. `visual-evidence-lifecycle-contract.md` Clause 2 adds a 30-day (43200-minute) orphan
  sweep each owning skill runs at its own Phase/Round 0, BEFORE minting its own slug, scoped only to
  ISOLATE run-scoped evidence (never a SHARE reusable cache or a committed module deliverable) -
  the ordering and the mtime bound together mean the sweep can never touch a concurrent run's live
  directory. 12 new guard tests added (3 new files), each proven red against the pre-fix text before
  being fixed green.
- `odoo-ai-agents` - the prior GC fix covered only three `visual/` evidence subpaths; the state
  root's garbage-collection gap was repo-wide. `visual-evidence-lifecycle-contract.md` gains a
  Clause 3 that enumerates and classifies every Tier-2 ISOLATE subpath in
  `state-root-resolution.md`'s own table (exhaustive, cross-checked by a new structural test):
  eligible subpaths reuse one of the two existing bounds (a 24h crash-backstop when a subpath
  ALREADY self-deletes at its own terminal status - `wave/<slug>/`, `visual/<run_id>/<module>_staging/`
  - or a 30-day deliberate-retention bound otherwise); `recon/<slug>-<date>/` is excluded because a
  competing, already-tested contract (`scouting-persistence-contract.md`) already states "never
  delete" for it; `run-<id>.json` is excluded because it can legitimately sit untouched for an
  unbounded period while a run is merely paused at a human gate, not abandoned - mtime is not a
  reliable liveness signal there, so sweeping it risks destroying a still-resumable run's
  blackboard, a known gap recorded rather than papered over; `brainstorm/state.json` is marked
  not-applicable (a singleton file, not a per-run accumulating path); the SHARE tier is explicitly
  declared out of scope by design (a reusable cache's whole value is surviving across runs - a
  staleness check belongs to that cache's own contract, never a TTL delete here). `worklog/` and
  the 13 workflow `output_dir` trees are swept ONCE each, at the shared chokepoint every consumer
  already goes through (`worklog-contract.md`, `workflow-chaining/SKILL.md` Phase 0) rather than at
  every individual consumer; the nine remaining individually-owned subpaths
  (`git-rebase/`, `forward-port/`, `modules-upgrade/`, `coding/`, `reviews/`, `pr-monitoring/`,
  `i18n/`, `visual/videos/`, and `visual/<run_id>/<module>_staging/`) each gained their own sweep at
  their owning skill's Phase/Round 0, citing Clause 3 rather than restating it. Caught during
  implementation: a naive sweep of `visual/`'s own top level would have deleted the sibling
  `current/`/`qa/`/`debug/`/`screenshots/`/`videos/`/`baselines/`/`doc/` trees wholesale the moment
  their own directory mtime went stale - `odoo-doc-illustration`'s crash-backstop now explicitly
  excludes all seven by name so only an actual abandoned `<run_id>/` directory can match. 10 new
  guard tests added (1 new file), including a structural cross-file consistency check that reddens
  if a future ISOLATE subpath is added without a corresponding Clause 3 classification.
- `odoo-ai-agents` - closed the remaining 13-entry `WORKTREE_PATH` shrink-only allowlist in
  `test_dispatch_brief.py` (now empty): `odoo-icon-designer`/`odoo-icon-design`,
  `odoo-marketing-writer`/`odoo-user-doc-writer`/`odoo-doc-illustration`, `odoo-data-migration`,
  `odoo-test-writing`, and `odoo-onboarding` now receive an explicit `WORKTREE_PATH` from their
  dispatcher instead of inferring their write location from ambient cwd; `odoo-doc-illustration`
  also stops truncating its `INSTANCE_HANDLE` to `<db>:<port>` and forwards `addons_path` as
  `ADDONS_PATH` so `odoo-marketing-writer`/`odoo-user-doc-writer` can run the Addons coverage
  assertion (`instance-handle-contract.md`) before capturing. `odoo-installable-prober` and
  `odoo-qa-suite` needed no `WORKTREE_PATH` field (P2 predates worktree creation; the phase writes
  only a state-root test-case table, never the executable test files) and gained a citation instead;
  three more (`odoo-feature-cataloger`, `odoo-planner`, `odoo-doc-feature-map`) were frontmatter
  false-positives that write only under the state root and needed no change at all - each closed
  with a cited reason rather than a silent retention.
- `odoo-ai-agents` - `odoo-forward-port`'s P9 reference detail (`fp-phase-detail.md`) no longer
  mixes raw `allocator.py`/`odoo-bin` shell with the SKILL.md instruction to delegate to
  `odoo-instance`. The raw acquire/install/release recipe - and the sibling copy in
  `fp-merge-absorption.md`'s per-batch verify protocol, which both SKILL.md and fp-phase-detail.md
  point to as the "full protocol" - is replaced with the same `odoo-instance` dispatch-brief
  mechanism the sibling `odoo-modules-upgrade`/`odoo-git-rebase` pipelines already use, so an agent
  can no longer read two contradictory mechanisms for the same phase; only `odoo-instance-ops` (and
  the instance-touching HARD LEAVES named in `instance-handle-contract.md`) may call the allocator
  or `odoo-bin` directly. The P9 `WORKTREE_PATH` re-root added earlier in this PR now lands
  directly on the actual dispatch brief instead of sitting above dead raw-shell text that ignored
  it.
- `odoo-ai-agents` - `scripts/lib/resolve_project_dir.sh`'s `ODOO_AI_PROJECT_DIR`/
  `ODOO_AI_WORKTREE_DIR` override handling now strips ALL trailing slashes (matching `paths.py`'s
  `.rstrip("/")`), not just one (`${VAR%/}`) - an override ending in a doubled or tripled trailing
  slash previously resolved to a DIFFERENT state directory in the shell vs the Python resolver, and
  an override that was only slashes (e.g. `/`) crashed the shell path (`mkdir -p ''`) instead of
  canonicalizing to `/` like the Python side already did. New table-driven parity tests in
  `test_project_dir_resolution.py` cover none/single/double/triple trailing slashes and the
  all-slashes case for both override variables.
- `odoo-ai-agents` - replaced four substring assertions across `tests/`
  (`test_run_harness_wave_hardrules.py`, `test_worktree_graph.py`,
  `test_coder_coordinator_topology.py`, `test_spawner_completion_contract.py`) that named a
  cardinality rule ("exactly one PR", "one odoo-coder per module", "exactly one level") without
  protecting it - each was equally satisfied by policy-INVERTING prose (e.g. "one PR per wave",
  "more than one odoo-coder per module", "more than one level") because the checked phrase was a
  literal substring of its own inversion. Each now pairs a positive regex anchored on the actual
  cardinality claim with an explicit rejection of the known inversion phrase.
- `odoo-ai-agents` - `README.md`'s "Per-persona quick-start guides live in `docs/personas/`" read as
  a claim that all 9 persona buckets `odoo-intake` routes to have a guide there; only 5 do
  (`docs/personas/` is never Read by any skill/agent/snippet/command/workflow/hook at runtime -
  confirmed a curated, human-facing subset, not a routing dependency). Reworded to state it is a
  subset and point at `docs/setup.md`'s already-accurate enumeration. `tests/
  test_persona_docs_consistency.py` gains a structural divergence guard (`PERSONA_DOC_DOMAIN`, an
  explicit doc-name -> router-domain map): a persona doc added/removed without updating the map, a
  half-authored language pair, or a mapped domain the router (`workflows/_schema.md`'s 9-value
  `domain` enum) no longer recognizes now fails 3 new tests instead of drifting silently. The 4
  existing dev.md/dev.vi.md-only SSOT-consistency tests (enumerated-identifier survival, safety-clause
  survival, structural-parity, tool-still-exists) are widened to run over every persona pair, not
  just dev - 0 additional findings today (the other 4 personas use a bare-name tool-listing format
  the row scan does not match yet), but no longer blind to the same drift if they adopt it later.
- `odoo-ai-agents` - closed a second, previously-unfixed instance of the shell/Python trailing-slash
  divergence: `_home()` (`scripts/lib/paths.py`, `scripts/lib/allocator.py`) did not strip ANY
  trailing slash from `$ODOO_AI_HOME` before joining it with `projects/<repo-key>`, while
  `resolve_project_dir.sh`'s `_project_dir_home` stripped exactly one (`${ODOO_AI_HOME%/}`, then the
  caller's own `${home%/}` cancelled a second one) - measured, a bare `$ODOO_AI_HOME` (no explicit
  override) ending in a doubled or tripled trailing slash resolved to a DIFFERENT SHARE/ISOLATE
  directory string in the shell vs the Python resolver. `resolve_instances.sh`'s
  `_odoo_ai_global_instances`/`_odoo_ai_runtime_dir` had the matching single-strip gap (coincidentally
  non-diverging today only because of how they append the `instances.toml`/`runtime` suffix). All
  four call sites now fully normalise trailing slashes (all-slashes falls back to `/`), matching the
  override-handling fix already shipped. New table-driven parity tests in
  `test_project_dir_resolution.py` (`test_odoo_ai_home_trailing_slashes_normalise_identically_share`/
  `_isolate`) extend the existing none/single/double/triple-slash suffix table to the bare
  `$ODOO_AI_HOME` root, not just the explicit-override case.
- `odoo-ai-agents` - `README.md`'s `### Skills (53)` section header had drifted from the
  top-of-file blurb, the `Skills` table's own 52 rows, and the actual `skills/*/SKILL.md` count
  (52) - `skills/_shared/` is a shared resource library with no `SKILL.md` of its own, not a
  skill, but the header counted it as one. Fixed the header to 52. This is the fifth hand-fixed
  count-drift instance in this PR (after two topology values and the forward-port phase set), so
  instead of a sixth one-off fix, a new guard (`tests/test_readme_inventory_counts.py`) computes
  every top-level plugin inventory count README.md states as a number - skills, agents, commands,
  declarative workflows, persona buckets - straight from the filesystem (or, for persona buckets,
  from the README's own enumerating table, since no independent on-disk registry exists) and fails
  naming the exact claimed-vs-computed mismatch.
- `odoo-ai-agents` - the README count-drift bug had already escaped past the README:
  `snippets/continuation-contract.md`'s own header comment stated "pasting the block into 31
  SKILL.md + 4 agent files" - the real counts were 50 and 21, off by roughly 2x and 5x. Separately,
  `snippets/gemini-gem-instructions.md`, `snippets/openai-gpt-instructions.md`, and
  `snippets/jetbrains-mcp-config.md` each hardcoded "31 tools + 9 MCP Resources" OUTSIDE their own
  `<!-- BEGIN/END GENERATED TOOLS -->` markers - numerically correct today, but a count `make gen`
  never touches, unlike the generated section a few hundred lines below it in the same files. All
  four now describe scope by what makes a file a member (grep the literal snippet path) or point at
  the file's own generated section / `generator/server-surface.json` instead of restating a count.
  A new guard, `tests/test_agent_facing_inventory_counts.py`, extends the README-only check to every
  snippet/skill/agent/command/workflow file across all plugins so this class cannot resurface there
  unnoticed again.
- `odoo-ai-agents` - the "OSM session-pin race" false-scope claim - pins scoped to the API key
  alone, not the calling agent or session, when the server actually shares each pin per
  `(api_key_id, mcp_session_id)`, i.e. per MCP session - that `e107561` corrected in
  `concurrency-guard.md` had the SAME wrong wording surviving, unchanged, in 15 other files it
  never touched: 6 agents
  (`odoo-backend-debugger`, `odoo-instance-ops`, `odoo-intent-extractor`, `odoo-translator`,
  `odoo-ui-debugger`, `odoo-ui-reviewer`), 4 skill/reference files (`odoo-debug/SKILL.md`,
  `odoo-demo-recording/SKILL.md`, `odoo-visual-regression/SKILL.md`,
  `odoo-git-rebase`/`odoo-forward-port`'s `*-phase-detail.md`), 3 IDE snippets
  (`cursor-rules.md`, `gemini-gem-instructions.md`, `openai-gpt-instructions.md` - all hand-authored
  prose outside their `<!-- BEGIN/END GENERATED TOOLS -->` markers), and `docs/setup.md` plus BOTH
  `docs/personas/dev.md` and its Vietnamese mirror `dev.vi.md`. This is the SAME claim
  `CHANGELOG` already recorded fixing once before (#253, v2.6.0, "per API key" -> "per live MCP
  session") - it regressed a second time because every prior guard bound only the ONE file it was
  written against, not the claim itself. Most sites now POINT at
  `concurrency-guard.md`'s "OSM session-pin race" section instead of restating the scope (agent
  files shrank or held flat - no restatement grew); `docs/setup.md` and the two persona docs, whose
  audience is not Claude-Code-only, restate the correct `(api_key_id, mcp_session_id)` per-session
  scope instead of pointing at a Claude-plugin-internal file path. A new repo-wide guard,
  `tests/test_no_api_key_only_scope_claim_anywhere_in_repo` in
  `tests/test_agent_facing_guidance.py`, structurally matches the CLAIM (an "API key" token
  within a tight window of scope vocabulary - `per`/`scoped`/`keyed`/`alone`/`state`/`racy`/`pin`/
  Vietnamese `theo` - with no genuine session-scope proof, e.g. `mcp_session_id`/`MCP session`/
  `session-scoped`, within 300 characters either side) across every markdown file in the repo, not
  one file or one sentence, so this class cannot resurface unnoticed a third time. Proven red
  against the pre-fix tree first: 28 findings, one per site above (a table row or heading counts
  once per file it recurs in).

## [4.18.1] - 2026-07-28

### Fixed

- `odoo-ai-agents` - setup step `32-permissions-state-root` no longer emits a `Write(<path>)`
  permission rule; the `Edit(<path>)` rule it already writes covers every file-editing tool, Write
  included. Claude Code's file-permission layer matches path rules on `Edit(path)` ONLY, so the
  `Write(/$ODOO_AI_HOME/projects/**)` entry matched nothing while making the CLI warn at every
  launch ("Permission allow rule (`.claude/settings.json`): `Write(...)` is not matched by file
  permission checks - only `Edit(path)` rules are"). The warning was self-healing against the user:
  `hooks/ensure-state-root-permissions.sh` re-runs this step's `check` on every SessionStart, so
  deleting the offending entry by hand failed `check`, the hook re-applied it, and the warning came
  back on the next launch - the reported symptom being a hand-fix that "keeps reverting". The rule
  set drops from 5 to 4 (`Bash` x2 + `Read` + `Edit`); effective permission coverage is UNCHANGED,
  since `Edit(/$ODOO_AI_HOME/projects/**)` was already present and is the rule that actually binds.
  A regression test now fails the moment a `Write(` path rule reappears in the step's rule SSOT.
- `odoo-ai-agents` - `05-prereq-check.sh` (both the Python instance-list join and the bash `IFS`
  split) and `50-instance-spinup.sh`'s `IFS` split now use comma - the separator Odoo's own
  `--addons-path`/`addons_path` convention uses - instead of colon, so a 2+-entry addons_path
  resolves to its actual path list instead of being mis-split into bogus fragments.

## [4.18.0] - 2026-07-25

### Changed

- `odoo-ai-agents` - the advisory git-delegation reminder hook (`remind-delegate.sh`) no longer
  returns `permissionDecision: "allow"`; it now returns `"defer"` so the tool call falls through to
  normal permission evaluation while still attaching its reminder. The old value silently
  AUTO-APPROVED the exact git mutation the hook exists to discourage, defeating the repo's strongest
  stated boundary. BEHAVIOUR CHANGE: this INCREASES main-agent permission prompting mid-run - that
  is the correct behaviour (the hook was suppressing prompts it had no business suppressing). The
  new optional setup step below pre-allows the narrow state-root traffic that made up most of them.
- `odoo-ai-agents` - `odoo-planning` now calls `EnterPlanMode` AFTER both planners
  (`odoo-planner` + `odoo-doc-planner`) return and immediately before presenting the plan, instead
  of before dispatching them. Subagents inherit the caller's permission mode, so opening Plan Mode
  first blocked/prompted the planners' state-root writes on every run. The
  `planning-gate-contract.md` WHEN clause is amended accordingly: enter before the first
  git-TRACKED or otherwise irreversible effect and always before presenting, NOT before authoring a
  plan artifact that lives only under the state root. This reverses the timing half of a prior fix
  while preserving its other two invariants (exactly one enterer; no caller may pre-open). The three
  sibling orchestrators (`odoo-forward-port`, `odoo-git-rebase`, `odoo-modules-upgrade`) already used
  this shape and are unchanged.

### Added

- `odoo-ai-agents` - optional setup step `32-permissions-state-root` (and its SessionStart wrapper
  `ensure-state-root-permissions.sh`) that pre-allows exactly the narrow `~/.odoo-ai` state-root
  traffic executor agents need (the two `resolve_project_dir.sh` argument forms plus reads/writes
  under `projects/**`). It NEVER grants write access to `bin/`, `venvs/`, `node_tools/`,
  `setup-scripts/`, `runtime/`, or `instances.toml`, never writes `deny`/`ask`/
  `additionalDirectories`, and never touches `mcp__odoo-semantic` (owned by the connect command).
  It is honoured by `ODOO_AI_NO_AUTO_PERMS` and instructs a single restart, mirroring the browser
  permission step. Plugin-agent frontmatter cannot reduce prompting on its own: the build IGNORES
  `permissionMode`/`hooks`/`mcpServers` on plugin agents (contract docs corrected to say so).

### Fixed

- `odoo-ai-agents` - browser QA and debug evidence is no longer written into the executor's current
  working directory (where it created untracked files that were committed by accident).
  `odoo-qa-tester` and `odoo-ui-debugger` now write every screenshot/snapshot under
  `<ISOLATE_DIR>/visual/qa|debug/<slug>/` inside the `~/.odoo-ai` state root. Root cause was
  twofold: the capture instructions named no destination, and where they did the key was wrong - the
  chrome-devtools key is `filePath`, not `path`/`filename`, and its schema silently ignores unknown
  keys, so nothing was written and the agent improvised a cwd-relative name. `ISOLATE_DIR` is now
  threaded through all five dispatch paths; a three-bucket capture-destination rule keeps committed
  deliverables (`static/description/`, `doc/index.rst`) reachable only by an explicit copy; the
  refusal fallback fails closed (inline for chrome-devtools, BLOCK for playwright/pagecast).
- `odoo-ai-agents` - corrected the Odoo test base-class version windows (Fixes #177). `SavepointCase`
  exists v8-v16 (not "absent v8-v11"), had its class-level savepoint absorbed into `TransactionCase`
  at v15, and is REMOVED at v17 - so a surviving import on a v17+ target is BREAKING, not a warning.
  Adds the `TreeCase` (v11-v14), `HttpCaseCommon` (v14), `HttpSavepointCase` (v14-v16), and
  `Form`/`O2MForm` (v12+, relocated to `odoo/tests/form.py` at v17) windows. Retired the now-stale
  "distrust `test_base_classes`" directive: the OSM-server annotation bug it worked around was fixed
  upstream (`odoo-semantic-server#363`), and the tool is version-scoped and authoritative again. The
  facts now live once in `snippets/odoo-era-boundaries.md`; twelve inline restatements across skills
  and agents were replaced with cross-references.
- `odoo-ai-agents` - reconciled `odoo-planner`'s description, which claimed it "writes only the
  plan", against its own mandated worklog append, and removed a stale `plan_mode_active: true` on
  intake's single-module path that silently skipped the plan gate.

### Removed

- `odoo-ai-agents` - deleted a `SingleTransactionCase` deprecation warning that could never fire
  (the class is present and non-deprecated v8-v19), and the dead top-level `worklog/**` permission
  rules (the worklog lives under `projects/**` and is already covered).

## [4.17.1] - 2026-07-24

A zero-trust hardening sweep of the runtime instructions consumed by executor agents: 7 parallel
domain surveys, an independent adjudication pass, an adversarial solution review, and 4 post-change
reviews resolved 80+ verified defects across 100 files. Two of them change runtime behaviour - see
the first two Changed entries.

### Changed

- `odoo-ai-agents` - a multi-wave coding run now lands on ONE run-level `run-integration` branch:
  every wave cherry-picks onto it and AUTO-ADVANCES on a green cumulative close-gate, and the
  terminal `integrate` land-tail opens a SINGLE pull request once after the final wave. This
  replaces one squashed PR per wave, which produced N stacked PRs on unmerged bases and stopped for
  a human at every wave boundary. Hard rule 5 is reconciled accordingly: the branch push and PR
  open are part of drive-to-done, and the only L2 gate left in a coding run is the outward merge.
  There is still no auto-merge.
- `odoo-ai-agents` - browser exclusivity is now **one driver per MCP family** rather than a global
  single-flight. The previous rationale ("one shared Chromium regardless of family") was factually
  wrong: the six registered families are distinct processes with isolated profiles. Same-family
  exclusivity is retained; cross-family concurrency is bounded by the `concurrency-guard.md` pool
  cap plus an explicit RAM guardrail, since nothing actually enforces a browser RAM budget
  (`resource_limits.sh` caps `odoo-bin` only, not browsers).
- `odoo-ai-agents` - any DYNAMIC (unplanned) run node now gates at L2, not only source-writing
  ones; the static-node tie-break is the lowest node id.

### Fixed

- `odoo-ai-agents` - version boundaries re-grounded against the Odoo Semantic index (v8-v19):
  `patch()` is 3-arg at **v15/v16** and 2-arg only from **v17** - previously asserted as v16 in
  several files, which put the frontend coder and the code reviewer in direct conflict inside the
  same coding loop; `odoo.define()`, `web.Widget` and `AbstractField` are **not** removed at v16
  (loadable through v17, absent from the index by v18); `t-out` is v15+; the manifest `assets` dict
  is v15+; Hoot is v18+ and QUnit v17 and below; `check_access(operation)`.
- `odoo-ai-agents` - removed hardcoded vault folder paths from the sales skills in favour of an
  optional env-rooted, layout-agnostic read, and extended the pre-commit hook plus the
  confidentiality-scan CI job so that convention cannot return to a public repo.
- `odoo-ai-agents` - corrected the run-harness orchestration registry entry that still described
  the superseded per-wave landing model, and regenerated the orchestration map from it.
- `odoo-ai-agents` - collapsed facts that had drifted across files to one definition plus
  cross-references: the doc language resolver, the Med-tier acceptance depth, the browser pool cap,
  the MCP tool/resource counts in the IDE snippets, and the skill count in the Codex manifest.
- `odoo-ai-agents` - contract clarifications for executor agents: `WORKTREE_PATH` is load-bearing
  with no safe default, the coordination ledger root points at its SSOT instead of an inline git
  call, a stray `gate_tier` in a continuation block is now `risk_level`, `odoo-gap-analysis` routes
  buildable-but-trivial work onward instead of reporting DONE, and `odoo-acceptance` gains a
  bounded UNVERIFIED path distinct from its FAIL loop.
- `odoo-ai-agents` - guard tests retargeted to assert the new contracts rather than the old
  wording: the resource-teardown fingerprints now pin the per-family rule and go red if it is
  reverted, the agent-body convention test proves its own predicate can fail, and the wave-gate
  tests were tightened.

## [4.17.0] - 2026-07-21

### Added

- `odoo-ai-agents` - agent-role SSOT: every agent now declares a `leaf` or `coordinator` role in
  `skill_tool_deps.json`, backing a strict lint that fails an agent missing a role or missing its
  never-spawn self-declaration; a new advisory (non-blocking) leaf-guard nudge fires when a
  dispatched leaf reaches for `Agent`, a git-mutating `Bash` call, or `Skill(git-ops)`.
- `odoo-ai-agents` - `snippets/odoo-era-boundaries.md`, a new SSOT for Odoo version-era boundaries
  (legacy vs OWL-2 frontend, the `owl` 2.x library package rollout, the Hoot test framework, and
  the `SavepointCase` absorption point), consumed by the coding-guidelines index, the
  `odoo-coder`/architect read-before-write steps, forward-port, deprecation-audit, test-writing,
  risk-overview, and the UI-review era-detection step. A v8-v13 request now falls back to the
  14.0 baseline plus an OSM lookup at the call site instead of getting no guidance at all.
- The generator's spawn-truth and workflow lints - agent-role coverage, orchestrator-nl spawn
  detection, auto-skip-needs-`when:`, no-haiku-feature-verdict - and `check_workflows.py` are now
  enforced in CI (`make validate` runs both `--strict`; a dedicated workflows-check CI job was
  added), closing the gap where these checks existed but were warn-first or not run in CI at all.

### Changed

- `odoo-ai-agents` - corrected the `SavepointCase` era boundary to **v15** (`TransactionCase`
  absorbs the class-level savepoint there, not v16 as several docs previously stated) and the
  `owl` 2.x library package boundary to **v16**, across forward-port, deprecation-audit,
  test-writing, intent-extractor, the upgrade classification table, and risk-overview - all now
  citing the era-boundaries SSOT.
- `odoo-doc-illustration` now defaults the App Store landing layer to `TONE=marketing`, so a bare
  run pre-fetches marketing copy/catalog instead of hard-blocking on the marketing writer;
  `odoo-doc-walkthrough`'s scenario-capture mode gains the same walkthrough pre-fetch.
- `odoo-ai-agents` - reconciled producer/consumer handoff contracts across the upgrade, coding,
  and doc pipelines: `odoo-diff-comparator` now emits a per-module verdict (including `MIXED`)
  plus `whole_module_absorbed`/`absorbing_core_feature` flags, and `odoo-modules-upgrade` gates on
  that verdict instead of counting findings; `odoo-coder` now handles a `NEEDS_NEXT:
  odoo-instance` reply by self-provisioning inline and re-launching instead of stalling;
  per-module `doc_layer` now threads through `doc-plan.yaml` -> planner -> writer-launch (the
  run-level axis is the fallback, never the primary); dispatch briefs carry explicit
  `mode:`/`verify_mode:` keys.
- `odoo-ai-agents` - routing cleanup: duplicated natural-language triggers removed from
  `odoo-qa-suite`/`odoo-support-triage` (the owning workflows already carry them), several skills
  now name the `odoo-instance` skill front door instead of the raw `odoo-instance-ops` agent, and
  Out-of-Scope/handoff boundaries were corrected across forward-port, rebase, modules-upgrade,
  perf-audit, gap-analysis, and customization-inventory; command references in prose now carry a
  leading `/`.
- `git-toolkit` - the bounded-read allowlist is single-sourced in `git-delegation-decision.md`,
  with the `odoo-ai-agents` copy cross-referencing it instead of duplicating it; `bisect-run` is
  now classified as a reversible-write, distinct from the read-only `bisect-read`.
- `git-toolkit` - bumped to 0.6.0, formalizing this PR's git-toolkit changes.

### Fixed

- `odoo-ai-agents` - `detect-intent.sh` matched on unanchored substrings, so strings like
  "view-in-review" or "repo-in-report" could trip an unrelated domain bucket; matching is now
  word-boundary-anchored, and Odoo-specific hints are gated on an actual Odoo anchor.
- `odoo-ai-agents` - opt-in browser MCP families (playwright, pagecast, and their headed variants)
  were not auto-approved in-session because the permission matcher only recognized the
  fully-qualified tool name; it now also accepts the bare `mcp__<server>__` prefix.
- `odoo-ai-agents` - a conditional UI-review suggestion emitted via the deprecated
  `SUGGESTED_NEXT` field was silently dropped once a status block was present; it now goes
  through the fenced continuation `next:` array, which the parser actually reads.
- `odoo-ai-agents` - the `## MCP tools` generated-marker block was missing entirely from
  `odoo-i18n`, `odoo-qa-suite`, `odoo-test-writing`, and `odoo-icon-design`; the generator
  preflight now hard-fails when a registered, non-empty skill is missing the heading instead of
  leaving it silently unpopulated.
- `odoo-ai-agents` - `odoo-qa-suite` no longer claims, in its own body or the README, to launch
  the `odoo-test-writer` agent; it stays static/inline, matching actual behavior.
- `odoo-ai-agents` - dropped an orphan `budget.max_gate_l1_autopass` field from the
  workflow-harness schema documentation, and stale project-relative `.odoo-ai` narrative left
  over from the 4.16.0 state-root migration.
- `git-toolkit` - `github-operator` now hard-gates a merge to `main`/`master` on a green CI status
  instead of sourcing the gate from the nesting-protocol doc; `git-squash-push`'s human-confirm
  gate now sits before the destructive `reset --soft` step rather than only in front of the push.

## [4.16.0] - 2026-07-17

### Added

- Default `odoo-bin` memory + time caps on every scripted instance launch (init/update/test), version-general across Odoo v8-v19: a shell `ulimit -Sv` spine (the only guard that fires on v8-v11, where Odoo applies no RLIMIT_AS itself) plus `--limit-memory-hard` (which overrides Odoo's own 2.5 GiB default clamp on v12+). The cap defaults to `MemTotal x 0.5` floored at 4 GiB and is overridable via `ODOO_AI_LIMIT_MEMORY_HARD` (empty or `0` opts out). New `scripts/lib/resource_limits.sh` value resolver and `snippets/odoo-bin-resource-limits.md` policy SSOT; the long-running listener conf additionally carries `limit_memory_soft` + `limit_time_real`.
- Single namespaced `~/.odoo-ai/` state root with a two-axis model, replacing the per-project `./.odoo-ai/`: Tier-1 machine-global flat (lease registry, `instances.toml`, logs, `i18n.json`), Tier-2 SHARE-per-repo (`context.md`, designs, coordination, survey - converges across a repo's worktrees), and Tier-2 ISOLATE-per-worktree (run state, worklog, qa - distinct per worktree so the drive-to-done continuation hook's "one active run" invariant holds). New `scripts/lib/resolve_project_dir.sh` + `paths.py` resolver (shell/Python parity), `snippets/state-root-resolution.md` SSOT with the resolve-capture-substitute prose protocol and cross-worktree dispatch rule, and an idempotent, crash-safe SessionStart migration of any legacy project-local `.odoo-ai/`.

### Changed

- Every skill/agent/command now resolves its state paths through the resolve-capture-substitute protocol (resolve once via the resolver, substitute the captured absolute path) instead of a bare project-relative `.odoo-ai/` literal.
- Instance database names now carry a per-project discriminator (`odoo_<series>_<repo-key8>`), so two concurrent projects on the same Odoo series never share a database name in the machine-global catalog.

### Fixed

- Port-allocation boundary off-by-one: the allocator now reserves ALL catalog-declared ports when picking a pool, so a heavily loaded instance pool can no longer hand out the next instance's declared port to a concurrent session.
- Bootstrap-race where two never-migrated projects could both default to port 8069 and attach to the wrong Odoo server: fixed with eager catalog migration (distinct ports assigned up front) plus an instance-identity attach guard that fails closed rather than attaching to a foreign server.
- `--addons-path` was written colon-separated (PATH-style) into the allocator lease record; Odoo requires comma-separated addon directories, so the lease field is now comma-joined to match its sibling and Odoo's own expectation.

## [4.15.0] - 2026-07-17

### Added

- `odoo-ai-agents` - resource teardown before DONE: an execute-agent can no longer report DONE
  while a self-provisioned Odoo test instance or a browser page it opened is still alive, closing
  a RAM-leak source. The instance allocator now binds the server's process-group id (`server_pid`)
  onto the lease and launches the server under `setsid`, so release stops the whole process group
  (SIGTERM, then a bounded SIGKILL escalation) before dropping the database. Enforcement is two
  hooks: `enforce-teardown.sh` (SubagentStop) hard-blocks a DONE claim against a live
  self-provisioned lease and flags an open browser page as advisory, while `session-end-gc.sh`
  (SessionEnd) reclaims anything a crashed session left behind, with a 7200s TTL as the final
  backstop. The contract lives in one new SSOT, `snippets/resource-teardown-contract.md` (stages
  T0-T4), wired into the completion hub and every skill/agent that can open an instance or a
  browser page.

### Changed

- `odoo-ai-agents` - portability cleanup for the new resource-teardown eval assets: replaced
  machine-specific absolute paths with placeholders/module names so the eval set runs unmodified
  on any machine.

### Fixed

- `odoo-ai-agents` - the `test` verb no longer reports `TEST_RESULT=passed` when the run's only
  outcome was a SKIPPED test. It now counts skips, emits `TEST_SKIPPED`, lists the skipped test
  names in the findings file, and reports `TEST_RESULT=inconclusive` (`status:
  tests-inconclusive`) instead - a HOLD, not a pass. (#171)

## [4.14.0] - 2026-07-16

### Added

- `odoo-ai-agents` - deterministic instance readiness/completion detection (v8-v19): an `-i`/`-u` build keys off process exit plus a forced `Modules loaded.` completion marker (`--log-handler=<ns>.modules.loading:INFO`, `openerp` for v8-v9 / `odoo` for v10+) and a silent-skip failure-marker scan - exit 0 alone is not treated as proof of install; a listening instance detects readiness by a bounded HTTP poll of `/web/database/selector` (fallback `/web/login`), never by tailing a log left empty under `--log-level=warn`. The foreground and background (`wait-log`) completion checks share one SSOT marker set so they cannot diverge.

### Changed

- `git-toolkit` - bumped to 0.5.0, formalizing this PR's git-toolkit changes: `github-operator` inline PR-review fan-out recipe, and report-up-one-level (`git-pipeline-lead`/`git-operator`/`github-operator` report to the caller that dispatched them, never a hardcoded `main`).

## [4.13.0] - 2026-07-16

### Added

- `odoo-ai-agents` - `spawner-completion-contract.md` SSOT: a spawner that launches child agents
  blocks on a mechanical completion barrier, never reports DONE before its launched children
  finish, and reports up exactly one level to its launcher (`REPLY_TO`), never a hardcoded `main`.
- `odoo-ai-agents` - bounded architect peer reconciliation in `master-child-design-contract.md`:
  same-layer architects reconcile directly via lead-brokered `PEERS:` (2 round-trips), recording
  agreements in their own child TDD and escalating to the lead only on deadlock.
- `odoo-ai-agents` - instance `persist:` modes (`ephemeral` / `exclusive-running` / `shared-running`)
  with `run_id`-owned leases; an `exclusive-running` instance receives a unique allocator-issued
  port (never the shared `8069`) and the version-correct port flag resolved at runtime via OSM
  `cli_help` (v8-v19).

### Changed

- `odoo-ai-agents` - `odoo-code-review` PR mode now posts one inline comment per finding (every
  severity) with GitHub `suggestion` blocks via `git-toolkit:git-ops`, plus a separate verdict
  summary comment, instead of one consolidated comment.
- `odoo-ai-agents` - Plan Mode is entered by exactly one actor - the plan-authoring skill
  (`odoo-planning`), before it authors the plan; `odoo-intake` never enters Plan Mode.
- `git-toolkit` - `git-pipeline-lead`, `git-operator`, and `github-operator` report to the caller
  that dispatched them, never a hardcoded `main`, so a nested dispatch is not misdelivered.

### Fixed

- `odoo-ai-agents` - instance drop refuses a foreign or unowned-but-fresh lease without `--force`,
  preventing one session from dropping another session's live instance.

## [4.12.3] - 2026-07-14

## [4.12.2] - 2026-07-13

### Changed

- `odoo-ai-agents` - reinforce the domain-first framing across `odoo-backend-coder`,
  `odoo-code-reviewer`, and `odoo-solution-architect`: each now states explicitly that an Odoo
  change is typically a business-management problem, NOT a technical/engineering one (with
  engineering excluded from the owning-domain list). `odoo-modules-upgrade` P2 gains an explicit
  principle header - upgrading a module to a newer Odoo version is new-feature development, needing
  no backward compatibility with the prior version or the module itself, no migration script, and
  no version bump.

## [4.12.1] - 2026-07-11

## [4.12.0] - 2026-07-11

### Added

- `odoo-ai-agents` - `odoo-modules-upgrade` gains a MANDATORY P5.8 `odoo-acceptance` stage and
  `odoo-forward-port` gains a MANDATORY P12 `odoo-acceptance` stage - cluster-wide, narrow-escape
  only, so an upgrade or forward-port runs the same end-to-end acceptance rigor new-module
  development gets instead of stopping at install/test (upgrade) or verify-by-behavior
  (forward-port). Each stage computes its verify scope via `acceptance-scope.md` (the P1
  dependency graph for upgrades; OSM `impact_analysis` reverse-closure for forward-port), dispatches
  `odoo-acceptance` ONCE for the whole cluster/batch (never per module/commit), and its verdict - or
  the explicitly recorded narrow-escape - is presented alongside the human sign-off/merge decision
  so the upgrade or port is never marked DONE without it.

### Changed

- `odoo-ai-agents` - `odoo-intake` now ALWAYS delegates 3-block plan authoring to `odoo-planning`
  via the Skill tool, on both the Plan-Mode step and the trivial single-module `writes-files`
  path - intake never authors the plan inline. `odoo-planning` still emits the minimal
  `[code, review, integrate]` plan for a single-module change, so the trivial path stays lean; it
  is simply never hand-rolled by intake anymore.
- `git-toolkit` 0.3.1 -> 0.4.0 - every git agent gains the dispatch-brief `## Brief self-check` + N5/N6 delta
  via `git-nesting-protocol.md` (no cross-plugin dependency on `odoo-ai-agents`).

## [4.11.0] - 2026-07-11

### Added

- `odoo-ai-agents` - the agent dispatch-brief system: a caller-side `dispatch-brief.md` SSOT
  (10-field brief skeleton + role-family deltas) that every spawner skill now fills when composing
  a dispatch prompt, plus a graduated `## Brief self-check` (NEEDS_CONTEXT/BLOCKED) added to all 30
  agents so a leaf can push back on an incomplete brief instead of guessing.
- `odoo-ai-agents` - `odoo-code-reviewer` now self-escalates to `odoo-perf-audit` /
  `odoo-security-audit` / `odoo-deprecation-audit`, diff-scoped, when the reviewed diff crosses
  their trigger thresholds (access rules/controllers/raw SQL, high-volume model ops or a stored
  cross-relation `@api.depends`, or a deprecated-symbol count over threshold). Findings from the
  review and the escalated audits are merged via a new `review-severity-rubric.md`, with an
  ownership-transfer dedup rule so the same finding is never double-counted across the reviewer and
  an audit. The three audits gain an optional `SCOPE_FILES`/`CHANGED_SET` mode (default stays
  whole-module) so the diff-scoped escalation does not re-audit the whole module.

### Changed

- `git-toolkit` 0.3.0 -> 0.3.1 - neutral agent-launch terminology: prose no longer names one
  harness's spawn tool, using "launch an agent" / "agent-launch capability" instead, across
  `docs/architecture.md`, `skills/git-ops/SKILL.md`, `agents/git-operator.md`,
  `agents/git-pipeline-lead.md`, `snippets/git-model-tiers.md`, `snippets/git-nesting-protocol.md`.
  The two-level by-construction nesting rule is unchanged.

## [4.10.0] - 2026-07-10

### Fixed

- `odoo-ai-agents` - **dropping an Odoo instance database silently did nothing when Postgres was
  not on the ambient default port.** The database port is now threaded through `create`, `init`,
  `update`, `run-tests`, and `drop`, plus the `createdb` probe, and is carried in the instance
  registry, the lease record, and the instance handle. The port defaults to omitted - never a
  fabricated `5432` - so `PGPORT` and non-default clusters keep working. Unknown `--` flags are now
  rejected instead of silently swallowed, and every drop logs which cluster it actually hit and
  whether the database was removed or already absent. (#163)
- `odoo-ai-agents` - instance operations could not reliably locate the Odoo virtualenv and would
  fall back to guessing an interpreter. Setup now hard-gates a declared source-mode instance that
  has no working venv (opt out with `ODOO_AI_ALLOW_NO_VENV=1` for a loud warning instead), instance
  operations preflight the interpreter, and the resolution rules forbid using the system
  interpreter for anything that runs Odoo, its tests, or a migration.

### Added

- `odoo-ai-agents` - per-run ownership for Odoo instances. Each lease now records the owning run
  id, so a session can tell its own instances apart from another session's. Releasing a lease
  owned by a different run is refused unless forced; a leased database must be dropped through the
  ownership-checked release path, while a bare drop is reserved for unmanaged databases and is
  guarded by a new `assert-droppable` check. Lease tokens are redacted in listings by default
  (`--show-tokens` reveals them). The lease registry is stamped `schema_version: 2` and stays
  backward compatible with existing registries.
- `odoo-ai-agents` - a live task list is now created and maintained whenever execution of a
  multi-step plan begins, so progress is visible as work happens. It complements, and never
  replaces, the durable run state and the worklog.

### Changed

- `odoo-ai-agents` - the per-module coding coordinator (`odoo-coder`) now actively leads its
  workers: it tracks each work item, consumes every worker result, reacts to a worker blocked
  before integration within a bounded retry loop, then integrates, verifies, and commits.
- `odoo-ai-agents` - agent-facing instructions no longer name one harness's spawn tool; they say to
  launch an agent and let the runtime pick the mechanism.
- `odoo-ai-agents` - `odoo-coding` skill description optimized for triggering, measured against a
  27-case trigger eval (14 should-fire / 13 should-not, EN + VI, with adjacent-skill near-misses).
  The description now leads with the trigger condition ("Use when someone wants to build or change
  Odoo behavior and needs the code written") instead of an output boast, and hardens the DO-NOT
  routing with the two missing adjacent routes (`Planning/estimate -> odoo-planning`,
  `Hook point -> odoo-override-finding`) while preserving the sole-front-door / per-module
  `odoo-coder` dispatcher framing, the pushy "fire on ANY request even with no technical words"
  language, the full coverage list, and the Vietnamese triggers (1009 chars, under the 1024 cap).
  The checked-in trigger eval set grows 21 -> 27 cases and records the harness-isolation caveat
  (`--setting-sources project,local` to beat the installed plugin; precision is the high-confidence
  signal, recall is bare-env-depressed for a front-door orchestration skill).

### Removed

- `odoo-ai-agents` - the artificial agent-nesting depth cap and the rule forbidding a caller from
  launching the `odoo-instance-ops` agent directly. Provisioning may run inline in the caller's
  context or launch the agent; either way the instance hard rules apply. Only factual statements
  about the platform's own nesting limit remain. The `git-toolkit` separate by-construction
  nesting rule is unchanged.

## [4.9.1] - 2026-07-09

### Changed

- `odoo-ai-agents` - `odoo-intake` optimization pass: reconciled the fire/no-fire contract (a clear
  single-step match is deferred OR one-line-gated, never ungated - gate-before-execution has no
  exception); broadened routing row 6 so a lone capability question (incl. reported speech) hits
  `odoo-feature-check` instead of brainstorm; tightened the trigger description. Routing-classification
  eval 42/43 -> 43/43.
- `odoo-ai-agents` - `odoo-solution-design` optimization pass: description sharpened with the
  design-vs-`odoo-planning` (build order) and design-vs-`odoo-doc-walkthrough` (usage scenarios)
  near-misses; the `return_to` payload-mapping table moved to `references/return-to-payload.md`
  (progressive disclosure; SKILL body 450 -> 432 lines). Design-decision eval held at 24/24.

### Added

- `odoo-ai-agents` - `odoo-intake` routing rows 55-63 so every user-facing front-door skill is
  reachable (`odoo-perf-audit`, `odoo-security-audit`, `odoo-data-migration`, `odoo-customer-health`,
  `odoo-i18n`, `odoo-pricing-proposal`, `odoo-rfp-response`, `odoo-test-writing`, `odoo-instance`) plus
  collision-zones 18-21; refreshed the eval set 43 -> 54 with coverage + discriminator guards.
- `odoo-ai-agents` - `odoo-solution-design` gains an `evals/evals.json` (24 design-decision cases incl.
  adversarial) - the skill previously had none.

## [4.9.0] - 2026-07-08

### Added

- `odoo-ai-agents` - `odoo-deep-survey` gains a conditional, BOUNDED web-research phase and a
  zero-trust code-survey stance. Web research (Phase W) fires only when a decomposed sub-question has
  an external dimension (a third-party library/API, a standard, an ecosystem/version-landscape
  question) and is capped (at most a few haiku WebSearch fork workers + top reputable WebFetch each,
  one broad-then-targeted pass) - no loop, no adversarial N-vote harness, no dependency on the heavy
  built-in `deep-research` skill. Sources rank on an Odoo authority ladder (official source/docs/OSM/
  OCA > reputable blogs/library docs > low-trust forums) and every web claim is subordinate to
  OSM/source. A new `zero-trust-code-survey.md` snippet (scoped to deep-survey) makes descriptions
  (docstrings, comments, READMEs, prior reports, and OSM descriptive fields) CLAIMS to verify against
  the resolved source, never trusted as behavior - without inverting OSM-first (trust OSM structure,
  verify behavior). `web_findings` added to the survey synthesis schema.
- `odoo-ai-agents` - dedicated `odoo-test-writer` agent now OWNS all automation-test authoring
  (invoking the `odoo-test-writing` skill as its SSOT capability, INLINE, in its own context as a
  HARD LEAF). Every test-needing component LAUNCHES it for context isolation instead of invoking the
  skill inline or using a bespoke coder test-author mode: in the coding path the `odoo-coder`
  coordinator gains it as a THIRD teammate (`odoo-test-writer` + `odoo-backend-coder` +
  `odoo-frontend-coder`, test-first - the RED test authored FIRST, then the coders make it green;
  the coders no longer author tests), and `odoo-acceptance` (durable tour/HttpCase), `odoo-qa-suite`
  (runnable tests), `odoo-code-review` (coverage gate), `odoo-forward-port` / `odoo-git-rebase`
  (adapt-mode translation) launch it too. Tours are now reachable as a coding RED test (a full-stack
  work-item's failing test may be a tour/HttpCase); performance/load test authoring gains an explicit
  owner (`odoo-test-writing`, lightweight mode); and the false "`odoo-coding` does not route to
  `odoo-test-writing`" claim is fixed. Agent count 25 -> 26.
- `odoo-ai-agents` - module-primary decomposition (two-tier axis, SSOT reconciliation). The
  decomposition model is now MODULE-primary at every OUTER layer: `odoo-planning` / `odoo-planner` /
  plan-mode-schema / Phase P / `run-harness` plan, serialize, and iterate MODULES (the
  plan's Block 1 is a MODULE list; a coding RUN-DAG node is a wave of MODULES with
  `approach_kind: wave`; `run-harness` iterates the wave's modules and invokes `odoo-coding` per
  module). The
  WORK-ITEM is now an INTERNAL intra-module parallelization unit OWNED by `odoo-coder`: for its ONE
  module the coordinator splits the changes into 1..N disjoint-file-set WIs, runs INDEPENDENT WIs in
  PARALLEL and DEPENDENT WIs SEQUENTIALLY (backend before a frontend WI that binds it), and assigns
  each WI to `odoo-backend-coder` / `odoo-frontend-coder`. `skills/_shared/odoo-module-graph.md` now
  states this two-tier axis as SSOT. This closes the three latent WI-vs-module seams the prior
  investigation found: same-module split (impossible - outer unit is the module, one owner per
  module + worktree + integrated test + ledger entry), cross-wave WI cycle (impossible - a WI lives
  within one module), and the undefined RUN-DAG coding-node model (resolved - modules grouped into a
  RUN-DAG node with `approach_kind: wave`, preserving the Block 2 `Wave N` grouping run-harness
  already assumes).
- `odoo-ai-agents` - coder coordinator restructure (per-module coordinator). `odoo-coder` is
  the per-module COORDINATOR that `odoo-coding` launches for EVERY module (backend-only, frontend-only,
  or full-stack): it owns the module's internal WI breakdown, launches the new `agents/odoo-backend-coder`
  (backend hard-leaf writer, a verbatim split-out of the old backend coder incl. its `/test_lint`
  gate + dependency pre-flight) and `odoo-frontend-coder` (now instance-free: static
  `verify-frontend.sh` gate only) per WI (backend before frontend), owns the INTEGRATED whole-module
  instance test via `Skill(odoo-instance)` INLINE, and drives a bounded 3-iteration fix loop - then
  COMMITS the module itself by invoking `git-toolkit:git-ops` (Skill tool) and returns the SHA to
  the `odoo-coding` SKILL, which collects it and passes it up (`odoo-coding` no longer re-commits).
  The coordinator may launch MULTIPLE workers in parallel (one per independent WI - siblings at the
  same depth). Nested subagent dispatch (main -> odoo-coding -> odoo-coder coordinator ->
  backend/frontend worker) stays within the platform depth cap of 5, and coordinator<->worker
  `SendMessage` works without any experimental agent-teams
  flag. New setup version gate: Claude Code >= 2.1.172 (probed by `05-prereq-check.sh`; no
  experimental flag is set).
- `odoo-ai-agents` - front-door planning gate (SSOT). New `snippets/planning-gate-contract.md` makes
  the FRONT DOORS - `odoo-intake`, `odoo-brl`, and the `odoo-implement-feature` workflow - the single
  admission gate: each establishes an approved plan (routing non-trivial work through `odoo-planning`)
  BEFORE it dispatches any executor. Executors (`odoo-coding`, the `odoo-coder`/`odoo-frontend-coder`
  agents) are trusted pipeline stages: they consume plan inputs when handed them and
  never self-block for "no plan", which keeps them directly composable (e.g. review/debug autonomous
  fix loops, hotfixes). The snippet also owns the single gated migration carve-out (a front-door
  routing decision made by `odoo-solution-design`), the Plan-Mode enter/exit + `plan_mode_active`
  mechanics, and the drift-adherence rule (an executor handed a plan stops and re-plans if reality
  diverges). New guards: `tests/test_planning_ssot.py`, `tests/test_mandatory_plan_gate.py` (asserts
  front-door enforcement + executor silence), `tests/test_migration_carveout.py`,
  `tests/test_excision_no_duplication.py`.
- `odoo-ai-agents` - the `odoo-planning` plan artifact now carries a REQUIRED, human-legible ASCII
  module-dependency graph (`plan-mode-schema.md` Block 2): nodes marked `(NEW)`/`(existing)`, tagged
  with the execute-skill that builds each, grouped by wave, with `depends` direction rendered - so a
  human reviewing in Plan Mode sees build order + per-node skill at a glance. Data-derived from the
  design `dag_layers` / topological order, never hand-drawn. Guard: `tests/test_plan_mode_dep_graph.py`.
- `odoo-ai-agents` - cross-run / worktree module-coordination ledger. New
  `snippets/module-coordination-ledger.md` defines a shared, `git --git-common-dir`-rooted ledger
  (atomic `mkdir` claim, per-module status + heartbeat) so parallel runs and worktrees can tell an
  in-progress dependency from a genuinely-missing one; `odoo-coding` is the sole writer, the leaf
  coder stays ledger-unaware. Guards: `tests/test_dependency_preflight.py`,
  `tests/test_module_coordination_ledger.py`.
- `odoo-ai-agents` - `odoo-doc-illustration` now stages screenshots under a run/module-scoped path
  (`.odoo-ai/visual/<run_id>/<module>_staging/...`) with a skill-owned end-of-run cleanup, ending the
  cross-module screenshot clobber (GitHub #157). New `tests/test_doc_staging_scope.py`.
- `odoo-ai-agents` - `snippets/rst-validity-contract.md` plus a MANDATORY docutils self-verify render
  gate in `odoo-user-doc-writer` (renders each `doc/*.rst`, blocks on any docutils `system_message`),
  ending the invalid-RST output (GitHub #158). New `tests/test_rst_validity_contract.py`.
- `odoo-ai-agents` - opt-in browser-MCP wiring, with install separated from run. A new `odoo-setup`
  step wires the five opt-in browser families (playwright, pagecast, and the headed variants) into
  Claude at user scope on demand, with a documented `disabledMcpjsonServers` opt-out;
  `scripts/lib/browser-mcp-servers.sh` holds the pinned npx SSOT. New `tests/test_setup_wiring.py`.
- `odoo-ai-agents` - browser MCP packages are pre-installed on disk (not run). `odoo-setup`'s
  `20-browser-deps` step now caches all three pinned MCP packages plus the Playwright Chromium binary
  via `npm install --no-save --ignore-scripts` (disk cost only), so a later opt-in spawn has no
  download latency and zero idle RAM - install (disk, once) is kept strictly separate from
  register/run (RAM, only while a session using the server is open). Extended
  `tests/test_browser_deps_setup.py`.
- `odoo-ai-agents` - active build-monitoring so agents never idle-stall on a long build. The
  `odoo-instance-ops` agent gains an "Active-wait on long builds" HARD RULE (cross-referenced from
  create/init/update/run-tests): launch the `55-instance-ops.sh` build in the BACKGROUND, then poll
  `LOG_PATH` in a bounded loop with an allocator heartbeat until a TERMINAL marker appears - success
  (`Modules loaded.` / `Registry loaded` / exit 0 / `Initiating shutdown`) or failure (`Traceback`,
  ` CRITICAL `, ` ERROR `, `Failed to load registry`, `psycopg2.`, `ParseError`) - with the process
  exit code authoritative; on timeout it reports BLOCKED with the log preserved instead of hanging.
  A new deterministic `55-instance-ops.sh wait-log` verb (+ `_scan_build_markers` helper) makes the
  marker check reliable and testable; the running-server readiness probe stays on the HTTP-200 check
  in `50-instance-spinup.sh`. The `odoo-instance` skill relays the short form. New
  `tests/test_instance_ops_hardening.py`; extended `tests/test_instance_ops_script.py`.
- `odoo-ai-agents` - subagents can self-provision an Odoo instance UNDER the HARD RULES. The
  `odoo-instance` skill gains an INLINE LEAF-MODE: a dispatched leaf/subagent that lacks an
  `INSTANCE_HANDLE` now self-provisions by invoking `Skill(odoo-instance)` inline-mode - which runs
  the ops steps (allocator ephemeral lease + `en_US` union + Viindoo `to_base` + lint-module install
  + per-version `cli_help` grounding) INLINE in the caller's own context (no subagent spawned, zero
  added depth) - instead of a bare `scripts/lib/allocator.py` call that BYPASSED those HARD RULES.
  The skill stays the single owner of instance fan-out with two modes (dispatch mode for
  orchestrators; inline leaf-mode for leaves); HARD RULES stay single-sourced in the agent
  (cross-referenced, not duplicated). Consumers updated: `odoo-qa-tester`, `odoo-coding`,
  `snippets/instance-handle-contract.md`, `snippets/worker-brief.md` (leaf carve-out). A provided
  handle always wins. Retargeted `skills/odoo-instance/evals/evals.json`.
- `odoo-ai-agents` - closed a gap in the entry above: the `odoo-coder` / `odoo-frontend-coder`
  CODER agents were missed by the inline-leaf-mode sweep. Their own no-handle self-provisioning
  fallback (the backend lint gate's isolated instance; the frontend quick-smoke server) still
  called `scripts/lib/allocator.py acquire` directly, BYPASSING the same HARD RULES their own
  lint/smoke gate depends on - crucially the lint-module install union `/test_lint`+`/test_pylint`
  need to be INSTALLED, not merely tagged. Both agents' "Running odoo-bin" sections now
  self-provision via `Skill(odoo-instance)` inline-mode instead of the raw allocator call; the
  `odoo-coder` path derives its lint-gate verdict directly from the skill's returned
  `instance-ops` block. `snippets/instance-resolution.md` § Allocate now states up front that it
  is the low-level mechanism the skill uses INTERNALLY, not a recipe agents call directly.
  Extended `tests/test_instance_ops_hardening.py`.
- `odoo-ai-agents` - per-module acceptance criteria and test scenarios are now cleanly owned at
  DESIGN time, and `odoo-planner` no longer overclaims the independent QA oracle as a planning-time
  input. `odoo-solution-architect` §9 Acceptance Criteria is now MANDATORY one module-level AC block
  PER AFFECTED MODULE (one block per §1 per-module table row), with a new §9 INDEPENDENCE GUARD:
  `expected` values MUST be requirement-derived (hand-computed), NEVER phrased from OSM/code
  findings - mirroring the `odoo-qa-planner` code-read ban. §7 Test strategy's scenario table is now
  PARTITIONED PER MODULE even in single-mode multi-module TDDs (master-child already got this via
  per-module child TDDs). `odoo-planner` / `odoo-planning` now mark `QA_ORACLE` OPTIONAL and usually
  ABSENT at planning time (the oracle is authored later, at `odoo-acceptance` Phase 1, after coding)
  - at planning the plan only RESERVES the acceptance stage against the design's §9 Acceptance
  Criteria and wires the real oracle in when/if one already exists.
  `snippets/acceptance-oracle-contract.md` and `odoo-qa-planner` now cross-reference the §9
  INDEPENDENCE GUARD to make explicit that consuming `DESIGN_DOC` §9 does not violate oracle
  independence (the ban is on reading the implementation, not the requirement-derived design doc).
- `odoo-ai-agents` - the per-wave integration (fork-from-prior-integration per Block 2W, cherry-pick in module-DAG order,
  cross-cutting integrated review, cumulative regression close-gate, one squashed PR at the
  L2-squash-gate, and the saga rollback/resume) is now owned DIRECTLY by `run-harness` as its
  § Between-wave integration (completing decision R); there is no separate git-executor skill. A coding wave is a RUN-DAG
  node with `approach_kind: wave` that `run-harness` drives (it iterates the wave's modules, invokes
  `odoo-coding` per module - whose `odoo-coder` coordinator commits via `git-toolkit:git-ops` and
  returns the SHA - then cherry-picks + reviews + closes the wave). The `spawner-wave` spawn_class is
  removed from the generator SSOT (`skill_tool_deps.json` `_doc`, `check_orchestration.py`
  `VALID_SPAWN_CLASS` + `_derive_gate_tier`, `gen_surface.py` legend); the between-wave advance is L1
  (autonomous drive-to-done) while the squash/PR is the in-context L2-squash-gate and the downstream
  merge stays `odoo-pr-monitoring`'s L2 - all expressed as a run-harness NODE tier, not a registry
  field. The `wave-templates.md` knowledge (four topologies, saga/conflict-resolver pseudocode,
  cleanup checklist, execution-log + squash recipe) moved to
  `skills/run-harness/references/wave-integration.md`. Skill count 53 -> 52; the `test_wave_*` guards
  were retargeted/renamed to `test_run_harness_wave_*` (behavior preserved: between-wave advance L1,
  squash/merge human-gated, principal-branch-lock, cumulative close-gate anchor, per-module inline
  review). User routing is unchanged - a parallel/multi-module request still goes to `odoo-planning`.

### Changed

- `odoo-ai-agents` - `55-instance-ops.sh` init/update now default to `--log-level=warn` (quieter than
  Odoo's stock `info`), placed BEFORE `--extra` so a caller-supplied `--log-level` in `--extra` still
  overrides it; a caller ESCALATES to `info`/`debug` for deep debugging. The `test` verb keeps its
  `--log-level=test` default (the PASS/FAIL parser depends on it). Documented in the `odoo-instance`
  skill + `odoo-instance-ops` agent; extended `tests/test_instance_ops_script.py`.

- `odoo-ai-agents` - planning is now consolidated in `odoo-planning` as the single owner: the plan
  schema is re-owned in place, and the duplicated plan-mode / trivial-vs-full / plan-schema prose
  previously scattered across `odoo-intake`, its references, `odoo-planner`, `odoo-solution-design`,
  and `workflow-harness.md` is excised down to one-line pointers (each fact stated once). Planning is
  mandatory for all work - there is no trivial/inline bypass; the sole exception is the gated
  single-module migration carve-out. `odoo-implement-feature.workflow.yaml`'s trivial branch now
  routes `next: odoo-planning`.
- `odoo-ai-agents` - the specialist pipelines `odoo-forward-port`, `odoo-git-rebase`, and
  `odoo-modules-upgrade` now reuse the shared Plan-Mode gate (`snippets/planning-gate-contract.md`
  § Plan-Mode enter/exit) for their human-approval step instead of bespoke `EnterPlanMode`/
  `ExitPlanMode` prose; `odoo-intake` still routes to them by intent and does not double-gate. Their
  specialized plan content stays authored in-skill (a git-history / cluster-upgrade plan is not a
  module-build DAG, so it is NOT routed through `odoo-planning`), and the upgrade per-DELETE
  confirmation gate is preserved. The contract also states the `odoo-solution-design` ->
  `odoo-planning` ordering explicitly (planning is a downstream consumer of an approved design;
  trivial work skips design but still flows through planning). Guard: `tests/test_planning_ssot.py`.
- `odoo-ai-agents` - the build path is dependency-aware and crash-safe. `skills/_shared/odoo-module-graph.md`
  gains a NEW-module case (a module resolving to neither OSM nor disk sources its `depends` from the
  design `dag_layers`), and the `odoo-coder` agent runs a manifest-`depends` resolvability pre-flight
  before `odoo-bin -i/-u`, returning a clean `BLOCKED` instead of crashing on an unresolved dependency;
  the `odoo-coding` dispatch loop classifies in-progress-sibling vs genuinely-missing (consulting the
  ledger). Standalone self-derivation stays a normal path (no planning self-block; the gate is at the
  front door).
- `odoo-ai-agents` - `.mcp.json` now eager-starts a single pinned browser server
  (`chrome-devtools`, headless) instead of six `@latest` servers, cutting idle memory (GitHub #156);
  `scripts/lib/browser_prefixes.py` derives tool-allow prefixes from the full-family static SSOT so
  opt-in families keep their permissions. `odoo-doc-illustration` capture defaults to
  `chrome-devtools`; `odoo-demo-recording` / `odoo-produce-video` note pagecast as opt-in.
  `tests/test_browser_mcp.py` rewritten to protect the one-eager-server contract (the family
  invariants relocated to `tests/test_setup_wiring.py`, not deleted).

## [4.8.0] - 2026-07-06

### Added

- `odoo-ai-agents` + `git-toolkit` - universal git-ops delegation discipline. A Universal rule in
  `snippets/git-delegation.md` (mirrored in `CLAUDE.md`, kept in lockstep) binds EVERY actor - the
  main agent included - to route all git operations (stage, commit, push, branch, merge) through
  the `git-toolkit:git-ops` skill, which applies the DCO sign-off; a dispatched leaf worker never
  invokes git-ops (Nesting leaf-exclusion + `snippets/worker-brief.md` cross-reference). New
  `tests/test_git_delegation_boundary.py` guard scans the agent-facing docs (`CLAUDE.md`,
  `docs/authoring-skills-and-agents.md`) for a raw git command in a code span, with a carve-out for
  the confidentiality-hook `git config core.hooksPath` install.
- `odoo-ai-agents` - the coding path now always commits AND lands. `run-harness` Hard rule 6
  provisions a dedicated worktree before dispatching any source-tree-writing node; `odoo-coding`
  always commits via `git-toolkit:git-ops` and self-provisions a worktree when invoked standalone
  (the old "no WORKTREE_PATH -> make no commit" branch is removed); the `odoo-intake` inline
  micro-plan gains a terminal `integrate` land node (git-ops opens a PR -> `odoo-pr-monitoring`
  merges at gate-tier L2). `integrate` added
  to the `approach_kind` enum in `docs/reference/workflow-harness.md`. New
  `tests/test_coding_commit_ownership.py` guard.
- `odoo-ai-agents` - `odoo-icon-design` now verifies and commits its generated icon assets
  (`icon.png` / `icon.svg` / the manifest `icon` key) via `git-toolkit:git-ops`, self-provisioning
  a worktree when standalone (previously the assets were written but never committed);
  `odoo-icon-designer` (leaf) returns the file paths for the skill to commit.

### Fixed

- `odoo-ai-agents` - `scripts/lib/odoo_db.py` `_import_odoo()` now imports `<pkg>.tools` and
  `<pkg>.service.db` explicitly via the resolved package namespace, fixing an `AttributeError` on
  Odoo 19.0 (a bare `import odoo` no longer binds `odoo.tools`) that broke every through-Odoo
  database drop and left stale entries in `leases.json`; the fix also handles the v8/v9 `openerp`
  namespace and is covered by a red-before-green regression test. (#154)

## [4.7.0] - 2026-07-05

## [4.6.0] - 2026-07-04

## [4.5.0] - 2026-07-03

### Added

- `odoo-ai-agents` - new CORE snippet `snippets/access-groups-conventions.md`: the
  `ir.module.category` XML-id derivation algorithm (`base.module_category_<slug>` from the
  manifest `category` string) and the `implied_ids` privilege-ladder pattern that renders a
  permissions dropdown instead of orphan checkboxes (v8-v19, algorithmically stable). Wired into
  the coding-guidelines INDEX "Security" row across all 6 indexed series (14.0-19.0) + the
  top-level snippet catalog, `odoo-coder` (read-before-write list + a new self-review checklist
  line), `odoo-code-reviewer` D2 (a new "Access group hierarchy" lens), and `odoo-security-audit`
  (a new OSM round item).
- `odoo-ai-agents` - new gettext-placeholders convention (`snippets/odoo-version-pivots.md`): a
  multi-arg `_()`/`_lt()` call must use named `%(name)s` placeholders, never multiple positional
  `%s` - a hard `test_lint` failure (`gettext-placeholders`, E8505) from v18+, previously only a
  style preference on v14-v17. Wired into the coding-guidelines INDEX "Translations" row across
  all 6 series, `odoo-coder` (pivot-read list + checklist item), `odoo-code-reviewer` D5, and
  `odoo-backend-debugger` (a new diagnosis entry for the E8505 failure).
- `odoo-ai-agents` - `docs/reference/INSTANCE-ALLOCATION.md` gains **§6.2 Config-file isolation**:
  the agent-facing contract that every concurrent instance build is isolated by the allocator
  (unique DB name + private port pool + create-through-Odoo), and that neither instance-build path
  (`55-instance-ops.sh` CLI-flags-only, `50-instance-spinup.sh` unique-per-run temp `odoo.conf`)
  ever reads or writes a shared/default config file.
- `odoo-ai-agents` - `odoo-instance-ops` gains two data-driven HARD RULEs, both gated on a profile
  resolved-and-pinned via `check_module_exists`/`set_active_profile`/`profile_inspect` (never
  probed profile-less, to avoid falsely treating a vanilla-CE build as Viindoo): (1) union Viindoo
  `to_base` into the server-wide `--load` module list (never as an ordinary `-i` module) when the
  active profile carries it, with a local-source fallback for the v19 `cli_help` silent-default
  gap; (2) for any test-run build, install (not merely tag) `test_lint`/`test_pylint` from the same
  probe that appends their `--test-tags`. `skills/odoo-instance/SKILL.md` gains the `PROFILE`
  brief param that threads the resolved `viindoo_profile` through to the agent.
  `docs/reference/ODOO-TESTING.md` and `docs/reference/INSTANCE-LIFECYCLE.md` document the
  invariant (SSOT stays in `odoo-instance-ops.md`); the static lint-module version table in
  `ODOO-TESTING.md` is demoted to illustrative-only (the runtime probe is authoritative).
- `odoo-ai-agents` - `generator/skill_tool_deps.json`: `odoo-instance` + `odoo-instance-ops` gain
  `check_module_exists`, `profile_inspect`, and `set_active_profile` (min_server_version 0.6.0 ->
  0.13.1) to ground the two new HARD RULEs above; regenerated `## MCP tools` blocks.

### Fixed

- `odoo-ai-agents` - `odoo-planning` gains a **Plan Mode guard** keyed on a new
  `plan_mode_active` dispatch-brief flag (SSOT: `odoo-planning` § Plan Mode guard): when
  `odoo-intake` delegates 3-block plan authoring to `odoo-planning` while its own Plan Mode is
  still open, it now sets the flag so `odoo-planning` skips `EnterPlanMode` instead of
  double-entering (a harness error); the flag is defined and read only by `odoo-planning`, never
  inferred from `return_to`. Clarified that the on-the-fly execution task list is `run-harness`'s
  alone, created only when Agent Team mode (CHP) is on.

## [4.4.2] - 2026-07-03

### Changed

- `odoo-ai-agents` - **the i18n non-destructive core no longer uses `polib`.** `po.merge()` behavior varies by installed `polib` version (hard to control), so the merge-based reconcile is replaced by the "human" workflow: build a FRESH instance, LOAD `en_US` + the in-scope languages (so the existing `.po` populates the DB), RE-EXPORT (which reproduces the human translation), then RECONCILE by a **git-ops diff-review** - the skill delegates the diff of the re-export vs the committed `.po` to `git-toolkit:git-ops` (never runs git itself) and adjudicates every removed/changed `msgstr` as correct (term gone from source) or wrong (accidental loss -> BLOCK) before commit. Rewrote L2/L3 + validation gate 1 in the recipe SSOT, `odoo-translator` Round 2/4, `odoo-i18n` P3/P4, and the `odoo-modules-upgrade` P5.7 reconcile; the placeholder-integrity check is now per-entry (no full-file polib scan). Forward-port forwards translations by copying the source `.po` into the target `i18n/` before the load + re-export + diff-review (no polib lift). Trade-off noted in the recipe: the raw diff is export-format-noisy (header / reference-comment / reorder), so adjudication focuses on `msgid`/`msgstr` changes only.

### Fixed

- `odoo-ai-agents` - **`en_US` is now always loaded, and the `.pot` is always re-exported fresh** - two operational failure modes in the i18n + instance-build flows.
  - **`en_US` always active (i18n).** `odoo-i18n` P0 now unions `en_US` into the DB-activation set (`activation_languages = {"en_US"} union target_languages`) - none of its resolution tiers could produce it (Odoo ships no `en_US.po`), so a translation could run against a DB with only the target language loaded. The recipe SSOT gains **KT3** + `en_US` in every `--load-language` example; P4 + the `odoo-translator` reload precondition now require `en_US` too. Activation-only, never an `en_US.po` deliverable.
  - **`.pot` always fresh.** `odoo-i18n` P2 + the recipe now mandate re-exporting the `.pot` from the current code on every run (**new recipe gate 5**); reusing a committed/stale on-disk `.pot` silently under-merged new/renamed terms.
  - **Instance build guarantees `en_US`.** `odoo-instance` (`create` / `init` / `run-tests` fresh) now unions `en_US` into the activation set before dispatch, and `odoo-instance-ops` gains a HARD RULE to load it on every build even when the brief's `languages` is `none` (previously create/init never consumed `languages` at all). `INSTANCE-LIFECYCLE.md` documents the invariant. The two enforcement layers (instance build vs `odoo-i18n`'s own raw `odoo-bin` calls) are intentionally independent, not duplicates.
  - Forward-port's `odoo-i18n` dispatch brief now notes `TARGET LANGUAGES` is deliverable-only (`en_US` is unioned by `odoo-i18n` itself). Added `tests/test_odoo_instance_en_us.py` + `en_US`/`.pot`-freshness assertions to `tests/test_odoo_i18n.py`.

## [4.4.1] - 2026-07-03

### Changed

- `odoo-ai-agents` - **dispatched workers never run git, no exception.** Removed the
  "own-worktree add/commit/stash" carve-out for domain workers. The coders (`odoo-coder` /
  `odoo-frontend-coder`) and any other domain subagent now WRITE their files in the assigned
  worktree and RETURN the file list; they run zero git. The orchestrator that owns the worktree
  (`odoo-coding`) invokes the `git-toolkit:git-ops` skill to stage +
  commit that output and capture the SHA. Rationale: workers do not know the project's git/commit
  conventions, so git is delegated entirely to git-ops.
  - SSOT tightened: `snippets/git-delegation.md` (dropped the "Benign local writes" section) and
    `snippets/worker-brief.md` (no worker git at all - write files, return, orchestrator commits).
  - `odoo-coder.md` / `odoo-frontend-coder.md`: removed the own-worktree-commit exception and the
    blanket "git-ops for any git work" clause - the coder returns files, never commits.
  - `odoo-coding` (+ `wave-templates.md`, wave evals): the commit is now an
    `odoo-coding` -> git-ops step after the coders return, not a raw coder commit; the WI-SHA
    contract is preserved (odoo-coding obtains the SHA via git-ops).
  - `odoo-modules-upgrade` P4 (KEEP/REWRITE brief) no longer instructs the coder to commit; the
    commit is a git-ops step (matching the DELETE-absorbed branch). Scanner false-positives
    de-fanged in `odoo-icon-designer.md` and `odoo-git-rebase` phase-detail.
  - `tests/test_git_delegation_boundary.py`: `add` / `commit` / `stash` are no longer an inline
    allowance - they fail the boundary scan like any other mutation (red-before-green self-check
    flipped to match).

## [4.4.0] - 2026-07-02

### Changed

- `odoo-ai-agents` - applied the same optimize + sole-dispatcher + Sonnet-5-tier pass to the **i18n** and **instance** fronts.
  - **`odoo-i18n`**: added an explicit **sole-dispatcher** contract for `odoo-translator` (it was already the only caller in practice - this formalizes it and prevents drift) and named the `odoo-instance` skill as the way to acquire the required live instance (never the raw `odoo-instance-ops` agent). Fixed the P5 consistency-audit tier: was flat `opus`, now **sonnet default; opus ONLY when the terminology is domain/legal/regulatory** (e.g. accounting circulars) - never for module or language count alone (Sonnet-5 policy; P1/P3 already followed it). Description gains the "ONLY dispatcher" framing (971/1024). Added `skills/odoo-i18n/evals/evals.json`.
  - **`odoo-instance`**: added the durable `skills/odoo-instance/evals/evals.json` (the one item outstanding after the 4.3.0 pass, which had already added its sole-dispatcher contract, description clause, and orchestration SSOT fix). No model-tier table by design (instance-ops runs flat `sonnet`).
  - No reroute was needed on either front: `odoo-translator` and `odoo-instance-ops` had zero direct-dispatch bypasses - every caller already routes through the owning skill.

## [4.3.0] - 2026-07-02

### Changed

- `odoo-ai-agents` - optimized the `odoo-coding` skill and **centralized all Odoo coding fan-out** through it.
  - **Triggering description** broadened to cover the full coding surface (new model/field, computed/related/constraint/onchange, `create`/`write`/`unlink` override, access rights, migrations, OWL/JS widgets, SCSS/theme; English + Vietnamese) and hardened with an explicit **"DO NOT trigger for non-Odoo code"** negative, while keeping the `route-to` clauses. Under the 1024-char budget (1007).
  - **Sole-dispatcher contract (SSOT):** `odoo-coding` is now the ONLY component that computes the model tier and launches `odoo-coder` / `odoo-frontend-coder`. The remaining direct raw-coder dispatches were rerouted to **invoke the `odoo-coding` skill via the Skill tool** - `odoo-forward-port` (P8b adapt, Tier-C fallback, frontend-route), `odoo-modules-upgrade` (P4 adapt, dangling-reference sweep, OWL/QUnit routing), and `odoo-git-rebase` (P9 test-forward) - so `odoo-coding` owns the backend/frontend split, coder fan-out, model, and synthesis. Routing pointers (`odoo-icon-designer`, `odoo-planner`, the upgrade breaking-change catalog) and the orchestration SSOT (`generator/skill_tool_deps.json` -> regenerated `ORCHESTRATION-MAP.md`) were updated to match. `odoo-git-rebase` P8 was already on this pattern and served as the template.
  - **Model-tier policy (Sonnet 5, ~1M context):** raw size, file count, and blast radius alone no longer escalate to opus - a large single-domain module is Sonnet work. `opus` is now reserved for changes that reason across MULTIPLE hard business domains AND are entangled with many interacting modules (wide cross-module ripple / deep inheritance chain); `fable` stays the rare Custom-XL cross-module inheritance apex. README tier docs updated.
  - Added a durable triggering eval set at `skills/odoo-coding/evals/evals.json` (11 should-trigger incl. Vietnamese + 10 near-miss should-not-trigger). Triggering is guarded by the repo's test-enforced routing/disambiguation + description-budget tests (all green); the skill-creator automated trigger harness could not attribute triggering in the headless env (it keys on an ephemeral stub while the installed skill absorbs the query), so it was not used as the signal.
- `odoo-ai-agents` - extended the same sole-dispatcher discipline to the **testing** and **instance** fronts.
  - **`odoo-acceptance`** is now the declared ONLY dispatcher of `odoo-qa-planner` (oracle) + `odoo-qa-tester` (live executor). Removed the Out-of-Scope escape hatch that told callers to spawn `odoo-qa-planner` directly, and fixed the Phase-1 tier phrase so cluster width / scenario count alone no longer escalates the oracle model (Sonnet-5 policy: opus only for multi-hard-domain + heavy cross-module coupling). Live execution provisions via the `odoo-instance` skill, never the raw agent. Description updated to the "sole dispatcher" framing, under 1024 chars.
  - **`odoo-instance`** gained an explicit sole-dispatcher contract for `odoo-instance-ops` (formalizing behavior every phase-orchestrator already followed; deliberately NO model-tier table - instance-ops runs flat `sonnet`). Fixed the one-line orchestration SSOT drift where `odoo-modules-upgrade` listed the raw `odoo-instance-ops` agent instead of the `odoo-instance` skill (regenerated `ORCHESTRATION-MAP.md`).
  - Corrected stale docs that claimed `odoo-coding` dispatches `odoo-qa-planner` or authors its loop test via `odoo-test-writing` (`agents/odoo-qa-planner.md`, README, `odoo-test-writing` SKILL): in reality `odoo-coding` authors its own red test inline via a separate coder in TEST-AUTHOR MODE.
- `git-toolkit` 0.2.4 -> 0.3.0 - optimized the `git-ops` skill for **triggering coverage** and **delegation discipline**. The `description` now leads with the dispatcher contract ("it ROUTES and DISPATCHES ... it never runs the churn itself") and broadens the trigger surface to the common phrasings that were missing - `commit`/`stage`/`push`/`pull`/`clone`/`stash` - so plain "commit and push" reliably reaches the skill; kept under the 1024-char description budget. Added a **"Your job is to ROUTE and DISPATCH, not to execute"** directive to the skill body (INLINE bounded reads remain the sole exception; when in doubt, delegate) and listed `stage/commit/clone/init/stash` in the Step-1 REVERSIBLE-WRITE bucket + the SSOT `git-delegation-decision.md` SINGLE-DELEGATE examples so routing matches the broadened triggers. Behavior eval (5 routing scenarios x with/without the change) held at 100% correct dispatch with no over-delegation of trivial reads.

## [4.2.1] - 2026-07-02

### Changed

- Optimized the `description` (auto-triggering metadata) of 11 skills for triggering coverage and cross-skill routing, after a full routing audit of all 53 skills (the other 42 were already well-disambiguated and left untouched to avoid churn). All rewrites stay within the 1024-char cap, keep the `route to ...` / `DO NOT trigger` disambiguation contract, use ASCII hyphens, and add no trailing punctuation; no body, tool-surface, or workflow change. Fixes: restored Vietnamese diacritics on `odoo-rfp-response` and `odoo-pr-monitoring` (unaccented triggers under-fired for correctly-typed Vietnamese); added a missing Vietnamese trigger set to `odoo-brl` and the "where do I start / plan the whole thing" Vietnamese phrases to `odoo-intake` (also genericized a hardcoded version out of an intake example); added missing routing clauses so `odoo-code-review` defers dedicated performance/security deep-scans to `odoo-perf-audit` / `odoo-security-audit`, `odoo-perf-audit` defers runtime slowness to `odoo-debug` and holistic PR review to `odoo-code-review`, `odoo-qa-suite` and `odoo-test-writing` separate a non-executing test plan from runnable test files and live acceptance, `odoo-deprecation-audit` defers cluster rewrite / data-migration to `odoo-modules-upgrade` / `odoo-data-migration`, and `odoo-doc-illustration` / `odoo-doc-walkthrough` disambiguate the doc-tier (illustrated guide vs text scenarios vs feature catalog) plus add the Vietnamese "hướng dẫn sử dụng" trigger.

## [4.2.0] - 2026-07-01

### Changed

- Restructured the `odoo-code-reviewer` agent body into a reading-flow section order (Orientation -> Core principles -> Reading the brief -> workflow -> Verification gates -> Severity & scoring -> Output -> Review dimensions) and replaced the tech-layer failure-mode catalogue with 7 explicit **review dimensions** (D1 correctness/ORM, D2 security & access control, D3 performance & queries, D4 domain & business integrity, D5 conventions/version/maintainability, D6 frontend & view fidelity, D7 test quality). Absorbed Odoo-fit gaps from Anthropic's code-review lenses (secrets-in-code, `safe_eval`/unsafe deserialization, path-traversal/SSRF, concurrency/race, missing index + unbounded query, duplication/single-responsibility) and added a `### Summary` line to the review output format. Deduplicated the verdict/score rule and CI-gate mechanics to one SSOT each and dropped the redundant brief-inputs table. No tool-surface or contract change; all test-enforced invariants preserved.
- Renamed the required skill body section `## Persona` -> `## Role` across all 53 skills (+ `tests/test_skill_format.py`, `tests/test_odoo_i18n.py`, `docs/authoring-skills-and-agents.md`). A skill's `## Role` states the executor's operating role, audience, and scope - identity/persona/voice belongs in the dispatched agent's system prompt (`agents/*.md`), matching Anthropic/OpenAI/Google guidance and keeping persona in exactly one layer (SSOT). Reworded 6 skills whose section leaked first-person identity or voice (`odoo-pricing-proposal`, `odoo-customer-health`, `odoo-deal-followup`, `odoo-support-triage`, `odoo-discovery-summary`, `odoo-doc-walkthrough`) into role + audience + output-tone framing.

### Added

- Guard `test_skill_format.py::test_skill_role_declares_no_identity`: a skill's `## Role` must not declare an identity (`You are a/an/the ...`) - that phrasing is reserved for agent system prompts.

## [4.1.0] - 2026-06-30

### Added

- Module packaging & documentation suite: 3 skills (`odoo-icon-design`, `odoo-doc-feature-map`, `odoo-doc-walkthrough`), 4 agents (`odoo-icon-designer`, `odoo-feature-cataloger`, `odoo-doc-scoper`, `odoo-doc-scenarist`), and the `module-packaging` workflow - an end-to-end pipeline from feature catalog and usage walkthroughs to module icon, per-locale App-Store landing copy, scenario-driven screenshot capture, and manifest audit. Includes the `app-store-template.md` reference (sanitizer-safe Bootstrap-5 fragment, section map, image specs, manifest store-keys) for `odoo-doc-illustration`.
- Dependency-aware multi-module doc planning: `odoo-doc-planner` agent (branch-aware instance allocation, leaf-first incremental install, cross-cluster dedup); `odoo-planning` full-lifecycle 2-agent dispatch (code + doc/marketing); `module-packaging` per-cluster incremental provision-capture.

### Changed

- Split `odoo-doc-illustrator` into audience-pure agents `odoo-user-doc-writer` (end-user guide: walkthroughs, RST, i18n) and `odoo-marketing-writer` (landing copy: App Store index.html, sanitizer-safe Bootstrap-5); `odoo-doc-illustration` skill is the sole orchestrator (picks writer model, pre-fetches marketing copy, routes DOC LAYER); `odoo-instance-ops` reduced to a pure operator (provisions and drives the instance, no doc authoring).

## [4.0.2] - 2026-06-30

### Fixed

- Removed 2 stray agent entries (odoo-diff-comparator, odoo-review-scoper) from the orchestration SSOT (skill_tool_deps.json) - they are agents dispatched BY skills, not orchestrating skills; drops 2 misleading rows from ORCHESTRATION-MAP.md and clears the orchestration-check coverage findings (ORCH_STRICT now passes).

## [4.0.1] - 2026-06-30

### Added

- Agent Team mode completion-reporting (issue #139) - teammates push a structured completion report via `SendMessage` to the lead and to dependents when Agent Team mode is on, and the lead tracks teammates via the native task board (new snippet `snippets/agent-team-protocol.md`); silent fallback to cold-spawn behavior when off.
- `argument-hint` frontmatter on every skill (51) and command (9) - a double-quoted hint (e.g. `"[PR#|local|worktree:<path>]"`) shown in `/<name>` autocomplete to advertise the arguments each front door accepts, derived from each one's real input contract. A new guard (`tests/test_skill_format.py`: `test_skill_argument_hint` / `test_command_argument_hint`) makes the field mandatory and rejects an unquoted value (which YAML parses as a list, not a string). Documented in `docs/authoring-skills-and-agents.md`.

### Changed

- Git delegation in `odoo-ai-agents` now routes through the `git-toolkit:git-ops` skill: consumers invoke `git-ops` via the Skill tool instead of cold-spawning git-toolkit's specialist agents; the guard test (`tests/test_git_delegation_boundary.py`) enforces the new seam.
- `git-toolkit` 0.2.2 -> 0.2.3 - the 3 leaf agents can push a completion report in Agent Team mode (new snippet `snippets/agent-team-reporting.md`); still cannot fan out.
- `odoo-semantic-mcp` 1.0.0 -> 1.0.1 and `git-toolkit` 0.2.3 -> 0.2.4 - their shipped command/skill (`connect`, `git-ops`) gained an `argument-hint`.

## [4.0.0] - 2026-06-29

### Added

- New skill `odoo-planning` + agent `odoo-planner`: the EXECUTION-PLAN step between solution-design (HOW to build) and code (HOW to ship). The planner turns an approved technical design into a gate-able 3-block plan - a wave-batched module-DAG, the integration cadence, each module/stage wired to a SKILL, and the full lifecycle (code -> review -> doc -> PR -> monitor -> merge) - emitting effort / `est_agents` ESTIMATES only (the dispatched specialist skill owns the real model + count at runtime). This splits PLANNING out of the former monolithic wave so design, planning, and execution are three distinct gated concerns.
- New skill `odoo-pr-monitoring`: the post-PR lifecycle owner (a poller, NOT a blocking DAG node) - watches an opened PR's CI + review state and MERGES at the L2-merge-gate, routing ANY CI warning/error/fail through `odoo-debug` (root-cause first) then `odoo-coding` (the re-push stays human-gated). PR/CI reads, the merge, and post-merge cleanup are delegated to git-toolkit's specialist agents (routed through its `git-ops` front door).
- Real naming-morphology enforcement (`tests/test_naming_consistency.py`): the three-layer name rules (skill = capability noun; agent = actor noun; `odoo-` prefix unless allowlisted) were previously only CLAIMED in prose with no test behind them - which is how a `run-driver`-class offender (unprefixed AND actor-morphology used as a skill) slipped in. The rules are now test-enforced, with a red-before-green classifier self-check.

### Changed

- Orchestration split (planning separated from execution): the sequencer skill `run-driver` is renamed `run-harness` (the drive-to-done loop over the run-DAG).
- `check_orchestration.py` gate-tier derivation: a new `outward` flag (declared on `odoo-pr-monitoring` in `generator/skill_tool_deps.json`) makes an outward git merge/push a third L2 trigger alongside `instance_touching` and `spawner-wave`, so an outward-merging poller's correct `default_gate_tier=L2` no longer mis-warns as "should be L1".
- `git-toolkit` dependency-direction fix: genericized so the domain-agnostic provider library never names its consumer `odoo-ai-agents` (skills/agents/commands), with a new guard test `tests/test_git_toolkit_independence.py` that scans ONLY `plugins/git-toolkit/**` (the exact inverse of `test_git_delegation_boundary.py`; together a non-overlapping bidirectional guard). (`git-toolkit` 0.2.1 -> 0.2.2.)

### Removed

- **BREAKING:** the standalone slash command for user-invoked wave execution is removed. Wave execution is no longer user-invoked; it is now an internal step driven by `run-harness` after a plan is approved. This is the breaking change behind the major version bump.

## [3.34.0] - 2026-06-29

### Changed

- `odoo-instance` run-tests runner gains a `--mode fresh|reuse` flag (default `fresh` -> `-i`; `reuse` -> `-u`) so re-running tests against a database that already has the modules installed updates them instead of no-op'ing on `-i`, and a `--log-mode warn|info|debug|sql` flag to control Odoo log verbosity. The runner now returns structured findings - `TEST_FAILED` / `TEST_ERROR` / `TEST_WARNING` counts plus a `FINDINGS_PATH` file (failing-test names + traceback heads, with in-scope warnings listed separately) - so a caller can triage without re-parsing the raw log.
- SSOT (`scripts/setup-steps/55-instance-ops.sh`, `agents/odoo-instance-ops.md`, `skills/odoo-instance/SKILL.md`, `docs/reference/ODOO-TESTING.md`, `docs/reference/INSTANCE-LIFECYCLE.md`) and consumers (`snippets/test-execution-handoff.md`, `skills/odoo-test-writing`, `agents/odoo-coder`, `agents/odoo-code-reviewer`, and the `odoo-git-rebase` / `odoo-forward-port` / `odoo-modules-upgrade` run-tests references) updated to pass `mode` / `log_mode` and consume the findings.

## [3.33.1] - 2026-06-29

### Changed

- `odoo-code-review`: add `'field' in self._fields` to the runtime-presence-probing idiom list (pitfall #8), and add base-expose-overridable-hook guidance for the inversion case (a base model must not sniff `_fields` for a downstream-injected field) to the `field-presence-resolution` snippet.

## [3.33.0] - 2026-06-28

### Added

- New skill `odoo-acceptance`: end-to-end acceptance orchestrator (spawner-agent, instance-touching, L2 gate) that closes a change AND its blast-radius - maps the affected cluster (reverse `impact_analysis` closure -> risk-ranked verify-scope manifest), plans an INDEPENDENT oracle, EXECUTES it on a real running instance/UI across the cluster (CRUD + at least two roles + state transitions + search), and adjudicates PASS/FAIL/UNVERIFIED with evidence. Dispatches `odoo-qa-planner` (oracle) + `odoo-qa-tester` (live execute), runs a durable tour/HttpCase channel via `odoo-test-writing` + `odoo-instance`, and drives a bounded fix-loop via `odoo-debug` / `odoo-coding`.
- New agent `odoo-qa-planner`: independent acceptance-oracle author - turns a requirement/intent into an immutable `scenarios.md` (GWT, equivalence/boundary, negative paths, role/CRUD/state/search matrices, risk tier per scenario) and STRICTLY never reads the implementation to decide expected values.
- New agent `odoo-qa-tester`: live acceptance executor - drives the real Odoo UI across the affected cluster and rules each scenario PASS/FAIL/UNVERIFIED with screenshot / console / network evidence; browser-exclusive (serial), reads the oracle read-only, fixes nothing.
- New snippets: `acceptance-oracle-contract.md` (three-different-contexts anti-bias invariant: oracle author != code author != adjudicator), `acceptance-scope.md` (the blast-radius verify-scope manifest: reverse-closure -> risk rank -> `install_set`/`test_set`/`render_check_set`), and `test-execution-handoff.md` (writer != executor delegation, `INSTANCE_HANDLE` precedence, output-volume contract).

### Changed

- `odoo-qa-suite` re-scoped to STATIC-only release QA - a non-executing release test-plan, a pre-deploy checklist, and bug triage; the independent oracle and live execution/adjudication now route to `odoo-acceptance` (the `qa-suite` workflow, its evals, and the README row marked static/non-executing to match).
- `odoo-ui-review` / `odoo-ui-reviewer` expanded to ground a screen's structure before checking its render: `module_inspect(method='views')` now also surfaces WHICH view types an action exposes (form/list/kanban/pivot/graph/calendar/activity), and the render-check scope is widened to dependents (blast-radius) per `acceptance-scope.md`. Declares the previously-undeclared `impact_analysis` (Step 1b template/asset-bundle blast radius) and `find_examples` (view-type shape); `docs/odoo-ui-knowledge.md` gains a "grounding a screen's structure" section.
- `odoo-test-writing` expanded for tour/HttpCase + per-module JS-framework grounding: declares `test_base_classes` (base-class menu + `cr.commit()`-forbidden contract, incl. HttpCase), `find_test_examples` (test-only chunks, no production contamination), and `js_test_inspect` (QUnit vs Hoot mix + suite paths + tour registry). Server floor raised 0.13.1 -> 0.15.0 to cover the test-surface tools.
- Test-execution delegation retrofit (writer != executor; SSOT `snippets/test-execution-handoff.md`): `odoo-coder`, `odoo-frontend-coder`, and `odoo-code-reviewer` now reuse a passed `INSTANCE_HANDLE` for bounded lint-only runs and delegate any full module / cross-module suite (and browser tours / served-bundle JS) to `odoo-instance` instead of running heavy suites inline.
- Acceptance wired as an opt-in, L2 (human-gated) next step: `odoo-code-review` emits `next: odoo-acceptance` when a change's `render_check_set` reaches beyond the changed modules (dependents bind a changed symbol) or the UI dimension is left `DONE_WITH_CONCERNS`; the `odoo-implement-feature` workflow tail (DESIGN -> CODE -> REVIEW -> ACCEPTANCE) and `odoo-solution-design` route the gate through `run-driver`. Never auto-runs, auto-blocks, or auto-merges.
- `odoo-intake` routing updated: rows 34 / 47 and disambiguation row 13 distinguish `odoo-acceptance` (execute + adjudicate an oracle on a live instance/UI) from `qa-suite` (static test-plan/checklist doc, nothing run), `odoo-ui-review` (rate one rendered screen), and `odoo-code-review` (static source review).
- README artifact tables reconciled to the real surface (48 skills + 17 agents): added rows for `odoo-acceptance`, `odoo-qa-planner`, and `odoo-qa-tester`, plus the pre-existing-missing `odoo-forward-port` skill row and `odoo-gap-analyzer` agent row so the counts match `plugin.json`.

## [3.32.0] - 2026-06-28

### Added

- New agent `odoo-gap-analyzer`: the leaf worker that runs heavy gap analysis for one requirement cluster in its own context (keeping the main / team-leader context clean). OSM-first -> local-checkout 2-tier grounding (training-only grounding banned; rows that cannot be grounded are marked `grounded:unknown` / `BLOCKED`), and it writes a machine-readable findings file per cluster.
- SSOT for complexity -> model-tier selection added to `skills/_shared/concurrency-guard.md` (the haiku / sonnet / opus / fable principle); the gap-analysis agent, skill, and callers reference it instead of hardcoding a model.
- `docs/authoring-skills-and-agents.md` - in-repo skill/agent authoring guide (Anthropic conventions + repo rules); referenced from CLAUDE.md.

### Changed

- `odoo-gap-analysis` upgraded from an inline leaf into a spawner-agent orchestrator: it clusters requirements by functional area, fans out `odoo-gap-analyzer` workers (rolling-window, model chosen per cluster complexity), synthesizes and de-duplicates findings from disk, and emits a locked file-handoff artifact set under `.odoo-ai/gap-analysis/<slug>-<date>/` (`gap-report.md`, `gap-matrix.jsonl`, `gap-continuation-contract.json`).
- Wired the gap-analysis file-handoff into its downstream consumers: `odoo-solution-design` and `odoo-solution-architect` (new `GAP_MATRIX` input port), `odoo-pricing-proposal` and `odoo-rfp-response` (effort read from `gap-matrix.jsonl`), the `odoo-respond-bid` and `odoo-implement-feature` workflows (explicit file-path chaining), `odoo-brl` (seed / cross-check from `gap-matrix`), and `odoo-intake` (scope-first routing: gap before design).
- `odoo-ai-agents`: moved agent routing ("when to invoke") out of the 7 agent bodies into their `description` frontmatter, per Anthropic's subagent convention (the body is the agent's system prompt only); added a guard test (`tests/test_agent_body_convention.py`) and a CONTRIBUTING "Agent format" section so the split does not regress.
- `git-toolkit`: same agent-body convention applied to its 4 agents - routing now lives in `description`, the body is the system prompt. (`git-toolkit` 0.2.0 -> 0.2.1.)

## [3.31.2] - 2026-06-28

### Changed

- `git-toolkit` single-delegate model assignment: the three leaf agents now default to `model: sonnet` instead of `inherit`, so a single-delegate spawn no longer inherits the caller's model (often opus) for trivial git/github ops. New SSOT `snippets/git-model-tiers.md` maps each single-delegate op-class to a tier (haiku for mechanical reads, sonnet default, opus for destructive rewrites); the `git-ops` SINGLE-DELEGATE route now passes the Agent-tool `model` param + a `DISPATCH MODEL:` brief line and no longer relies on `inherit`. Inert inline model tokens stripped from one leaf agent's phase descriptions (an agent's own model is fixed at spawn; body prose cannot set it). (`git-toolkit` 0.1.2 -> 0.2.0.)
- `git-toolkit` `op=squash-push`: the squash-to-one + tree-identity + force-with-lease recipe is promoted into `snippets/git-squash-push.md` (composing the `git-safety-contract` S1/S6/S2 primitives) - removing an SSOT duplication.

## [3.31.1] - 2026-06-28

### Fixed

- `odoo-git-rebase` orchestration gaps (#115): P8 conflict resolution and review now dispatch the `odoo-coding` / `odoo-code-review` skills via the Skill tool instead of raw agents; reference the new `git-toolkit` S10 `rebase --continue` continue-driver; slug sanitization pinned; `rerere.autoupdate` set; a conflict-type taxonomy added; P8b symbol-survival + collection gate delegated (Explore / git-toolkit's read-only survey agent) with an explicit PASS/FAIL verdict; explicit pyflakes import-resolvability gate; `installable=False` guard; a shared `INSTANCE_HANDLE` (new `snippets/instance-handle-contract.md`) provisioned once via `odoo-instance` and forwarded downstream; run-tests verdict contract.
- `git-toolkit` conflict continue-driver (#115): new S10 step in `git-safety-contract` - never `--skip` on "no unmerged files" (only on an empty `--continue` patch); per-path resolution (UD/DD -> `git rm`, static add/add -> non-empty side, marker -> coder, rerere-resolved -> `git add`); `rerere.autoupdate` enabled. the local-mutation agent and the `conflict-resolution` reference cite S10 inline. (`git-toolkit` 0.1.1 -> 0.1.2.)
- Capability/gap pipeline guardrails (#121, client-side only): module-slug -> provider inference forbidden; per-claim provenance tags `[OSM-index]` / `[inferred]` with wording downgrade; absence-in-index transparency; new `snippets/ssot-extraction-contract.md` (verbatim extraction for SSOT source docs); recon-no-file-write guard in `odoo-intake`. Live-MCP cross-check intentionally out of scope (kept per PR #42).

## [3.31.0] - 2026-06-28

### Added

- `odoo-solution-design`: master-child design decomposition for large multi-module scope. `odoo-solution-architect` now supports four modes (`single` / `master` / `child` / `consistency`); `master` mode produces one master TDD (cross-module contracts, shared-symbol ownership, DAG layer order) then N child TDDs in `dag_layer` order under `.odoo-ai/designs/<master-slug>/`; machine-readable `index.yaml` is the routing SSOT for downstream consumers. Two-level design handoff (`DESIGN_DOC` = child spec, `MASTER_DESIGN_DOC` = hard-constraint master TDD) wired through `odoo-coding`, `odoo-code-review`, and `odoo-debug`. Contract SSOT: `snippets/master-child-design-contract.md`.
- `odoo-frontend-coder`: TDD-conformance gap fixed - agent now reads and enforces `MASTER_DESIGN_DOC` constraints in addition to the child `DESIGN_DOC` spec.

## [3.30.2] - 2026-06-28

### Changed

- Semantic-preserving compression of plugin runtime docs (agents / skills / commands / references /
  snippets / docs) across `odoo-ai-agents` and `git-toolkit` - terse prose, within-file dedup, and
  inline-copy -> existing-pointer trims. No `name`/`description` frontmatter and no behavior changed
  (verified: `make validate` + `make test` 946 passed, frontmatter byte-diff vs `master` empty,
  `make gen` idempotent). Per-plugin `COMPRESSION-REPORT.md` added. Realized ~2.6k token / ~0.76%
  reduction - the repo was already heavily SSOT-factored, so the safe headroom was small.

## [3.30.1] - 2026-06-27

### Added

- Forward-port conventions C1/C2/C3, folded into the existing merge-window SSOT `snippets/fp-merge-absorption.md` (no new snippet) (issue #126). **C1** - a forward-port never invents a `__manifest__.py` `version` bump; on conflict the target file's version wins. **C2** - a forwarded `migrations/<src-series>.a.b.c/` dir is retargeted to the target series (FULL form); the manifest is bumped only when the source version `<=` the target's current manifest (so the migration fires on already-deployed target DBs), grounded in Odoo `adapt_version`/`migration.py` (verified v17+v18); a legacy source-origin-only data fix keeps the source-series dir. **C3** - a bug pre-existing at the source series is carried faithfully forward and surfaced upstream (source-series issue), not inline-fixed; security/safety fixes go on the destination immediately. C1 and C2 are explicitly de-conflated, and a module made `installable` by a prior-series upgrade then forward-ported is re-set to `installable:False` when the target clean-tip was not yet upgraded. Same-series manifest-conflict analogue added to `odoo-git-rebase`. RED-before-green invariants in `tests/test_forward_port_hardening.py`.

### Changed

- `odoo-modules-upgrade` Rule A is now unconditional: a code-level upgrade never bumps the manifest `version`, never writes migration scripts (a genuine data-bearing case routes to `odoo-data-migration`), and restores `auto_install`/`application` only when an explicit `# TODO: Uncomment when upgrading` manifest breadcrumb (left by forward-port) directs - wiring forward-port and upgrade together.
- The backend code-quality gate is now Odoo's own lint test module - `test_lint` (v14+, renamed from `test_pylint` at v13) plus `test_pylint` on v16+ Viindoo profiles - run via `--test-tags` on an instance, instead of the OCA `pylint-odoo` package. `docs/reference/ODOO-TESTING.md` is the lint SSOT. Note: this requires a running instance (matching what Runbot runs); the previous fast no-DB static gate is removed.
- Consolidated `snippets/module-rename.md` into `snippets/upg-conventions.md` (net -1 snippet, no new files); its consumers repointed.

### Removed

- OCA support entirely, across skills/agents/snippets/scripts/docs - including `scripts/verify-backend.sh`, `scripts/odoo-pylintrc`, the per-series `lint` pins in `scripts/lib/odoo-python-matrix.json`, the OCA addons-path role in `scripts/lib/discover_odoo.sh`, and the `"OCA style violations"` `lint_check` routing keyword. Upgrade/manifest rules collapse to single Viindoo/Odoo conventions.

### Fixed

- The forward-port manifest version-bump gate no longer fires merely because a diff touches `migrations/` - the root-cause conflation of C1 (no bump) with C2 (migration-dir retarget) is removed from both `snippets/fp-installable-false.md` and `skills/odoo-forward-port/SKILL.md` (issue #126).

## [3.30.0] - 2026-06-27

### Added

- `git-toolkit` delegation: all git/GitHub operations in `odoo-ai-agents` now delegate to git-toolkit's specialist agents (routed through its `git-ops` front door) instead of running inline. New caller SSOT `plugins/odoo-ai-agents/snippets/git-delegation.md` documents the boundary and carve-outs; `git-toolkit` declared as an `odoo-ai-agents` dependency in `plugin.json`; boundary enforced by the new `tests/test_git_delegation_boundary.py`.

### Changed

- The three heavy pipelines (`odoo-git-rebase`, `odoo-forward-port`, `odoo-modules-upgrade`), `odoo-code-review`, and the read-only leaf agents (`odoo-diff-comparator`, `odoo-intent-extractor`, `odoo-installable-prober`, `odoo-review-scoper`) no longer execute git or `gh` CLI calls inline; they cold-spawn the appropriate `git-toolkit` agent. Bounded reads (e.g. `git log`, `git diff`) and a subagent's own-worktree `git add`/`commit`/`stash` are explicitly permitted to stay inline.

### Fixed

- `odoo-modules-upgrade` upgrade robustness (review R3 findings M2/M3/L1/L2/L3): RECONCILE new-mechanism detection now runs `suggest_pattern`/`find_examples` unconditionally for every KEEP feature so a new parallel core mechanism (new model/mixin/action on the same domain) is caught even when the feature's own API endpoint shows no `new` items; crash-safe checkpoint resume now uses explicit per-phase skip thresholds (P2 skips {absorbed..done}, P4 skips {adapted..done}, P4b skips {reviewed..done}, P5 skips {installed,done}) preventing a resume from overwriting already-adapted integration worktree work; commit consolidation base is now recorded from the git-ops converge step SHA instead of being re-discovered from an interleaved log; design-trigger condition list removed from `upg-phase-detail.md` P2b (SKILL.md § P2b is the SSOT; duplicate no longer drifts); DCO sign-off (`git commit -s`) made mandatory in the P4 coder brief for KEEP/REWRITE paths.
- `git-toolkit` safety contract gains S9 (worktree-always / principal-checkout-lock, mandatory for all delegated ops); git-toolkit's local-mutation agent now emits a `BLOCKED-CONFLICT` status with `conflicted_files` and `stopped_commit` fields to support the stateless conflict-resume loop at the orchestrator level.
- Hardcoded fork and upstream identifiers removed from `odoo-git-rebase`, `odoo-forward-port`, and `odoo-modules-upgrade` agent prose; these are now resolved at runtime via `git remote get-url origin`.

## [3.29.0] - 2026-06-26

### Added

- Context-Handoff Protocol (CHP), an opt-in 3-tier agent-dispatch optimization (issue #98). New SSOT `snippets/context-handoff-protocol.md`: Tier A `SendMessage`-resume of a previously-spawned worker (gated on a runtime capability probe: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, `SendMessage` tool present, target addressable, orchestrator is the team lead), Tier B `subagent_type: "fork"` for read-heavy fan-outs, and Tier C fresh-spawn + worklog as the always-correct SSOT fallback. The snippet codifies the fallback trigger matrix (silent/automatic/degraded-but-correct), async park-and-be-resumed semantics, the lead-is-address-authority contract, "no nested teams = roster only", a confidentiality guard (never frame a handoff payload as a "secret"), the worklog-as-SSOT invariant, and an invariant/cross-check-at-aggregation rule. Wired into `odoo-coding` + `odoo-code-review` (coder<->reviewer loop, Tier A), `odoo-forward-port` (P1 intent-extract fork + P8/P9 adapt Tier A), `odoo-deep-survey` and `odoo-brl` (read fan-out fork). New generator field `handoff: send-message | fork | fresh` in `generator/skill_tool_deps.json` (absent = `fresh`), a `[chp-tier-c-fallback]` lint in `generator/check_orchestration.py`, a `handoff` column in the generated `docs/reference/ORCHESTRATION-MAP.md`, and `tests/test_chp_hardening.py` (#98).

### Changed

- Removed obsolete "no Skill tool / no subagent / NL-dispatch only" prohibitions now that Claude Code supports multi-level agent nesting (depth cap 5; interior agents can spawn subagents; "no nested teams" = roster only) and self-manages resources (concurrency cap, rolling windows, queueing). Skills, agents, and commands may now dispatch via the Skill tool: `odoo-qa-suite`, `odoo-debug` (relabeled Orchestrator), `odoo-support-triage`, `workflow-chaining` (phase dispatch incl. spawner skills), the `odoo-coder` / `odoo-frontend-coder` / `odoo-solution-architect` agents (blanket Skill-tool bans dropped; execution-pipeline carve-outs kept as scope correctness, not nesting fear), the `odoo-run-brl` / `odoo-summarize-discovery` commands, and `docs/reference/workflow-harness.md` (fork-worker hard-rule narrowed to spawner-skills-only, internal inconsistency resolved). Genuine non-nesting/non-resource carve-outs preserved: the cherry-pick critical-section + principal-branch lock + human-confirm-merge, `odoo-brl` sequential-outer ordering for checkpoint/resume correctness, `odoo-intake` fresh-context run-driver dispatch, and browser-main-context constraints. `README.md` and `workflow-harness.md` updated to document the CHP model and the corrected nesting reality (#98).

## [3.28.0] - 2026-06-26

### Added

- `odoo-modules-upgrade` v8-v19 hardening (issue #117). New SSOT `snippets/odoo-version-pivots.md` - a version-pivot table for ORM/view/manifest/CLI/JS facts across v8-v19, verified against the on-disk codebase, that every version-specific statement cross-references instead of hardcoding a single source->target pair. New `snippets/upg-conventions.md` (profile-gated Viindoo conventions: no manifest `version` bump on code-level upgrade, no-data rename via `old_technical_name`, always-invisible view field XML comment from v18, `hr.employee` groups guard), `snippets/stored-write-survival.md` (`readonly=False` is not proof a written value survives a `@api.depends` recompute), and `references/runbot-parity-checklist.md` (version-keyed reproduction of the Runbot lint/test gates). New pipeline phase **P1d Transitive Symbol Survey** (grounds external-dependency symbols down to base/ORM/tools at the target version, emitting `blockers[]` consumed by the coder); new **RECONCILE** verdict (target-core data-divergence OR new-feature wire-in, routed to design); gated-on **P5.7** i18n reconcile phase; per-module commit consolidation as a supported capability. Pipeline-robustness gaps closed (worktree/base/`cluster_slug` definitions, MIXED routing, `installable:False->True` in the coder brief, demo version-range). Wired into `odoo-diff-comparator`, `odoo-solution-architect`, `odoo-code-reviewer`, `odoo-coder`, `odoo-instance-ops`, `odoo-ui-reviewer`, `odoo-doc-illustrator`, and `odoo-deprecation-audit` (#117).
- `snippets/python-naming-conventions.md` (issue #120): Rule A (no `l`/`O`/`i` single-letter variable names - pylint `C0104` blocks CI) applies to all distributions; Rule B (no arbitrary abbreviations) and Rule C (iterate `self` as `for r in self`, not `rec`) are Viindoo-profile-gated. Routed via the per-version INDEX "By task" Naming row + the snippets catalog, and wired with thin pointers into the coder/frontend-coder/reviewer/backend-debugger/ui-debugger agents and the `odoo-qa-suite` / `odoo-test-writing` skills (#120).
- `snippets/test-protection-contract.md` (issue #117 follow-on): a single source of truth for "what tests guard what" - for every model/view/method a change touches, use OSM to enumerate the protecting tests in three tiers (own-module, base/dependency, framework/lint gates `base.TestInvisibleField` / `hr.TestSelfAccessProfile` / `test_pylint` / `test_lint`); tiers (i)+(ii) are MUST-NOT-BREAK. `odoo-coder` and `odoo-frontend-coder` now run this pre-flight UNCONDITIONALLY (not dependent on a survey having run), and `odoo-deep-survey` cross-references the same snippet so survey and coder share one methodology (#117).

### Changed

- SSOT consolidation of the coding guidelines (issue #117 follow-on). New `snippets/orm-performance.md` (a stored compute aggregating a high-volume relation MUST use one grouped `_read_group`, never per-record `mapped()`), now loaded by the general `odoo-coder` together with `snippets/stored-write-survival.md` and the `odoo-version-pivots.md` pivot table - the general coder previously loaded none of them; `odoo-code-reviewer` and `odoo-solution-architect` now cross-reference the perf SSOT instead of restating it. The CORE always-invisible-field XML-comment rule (v18+) is surfaced for all distributions in the coding-guidelines catalog (previously reachable only via the Viindoo-profile-gated path), and `odoo-i18n` documents the `.po`/`.pot` `#. module:` comment requirement. Per-version coding-guidelines topic files (verbatim upstream RST mirrors) are left untouched (#117).
- Coding-guidelines reorganised so the INDEX is a true router (issue #117 follow-on). The root `coding_guidelines/INDEX.md` is now a pure catalog/router (rule content evicted to snippets); each per-version `<v>/INDEX.md` "By task" table maps a task to its topic file(s) + the relevant snippets + the `odoo-version-pivots.md` section, and the code/debug/review agents (`odoo-coder`, `odoo-frontend-coder`, `odoo-code-reviewer`, `odoo-backend-debugger`, `odoo-ui-debugger`, `odoo-solution-architect`) plus their skills now MUST read the version INDEX first and read ONLY the By-task-mapped files (token-aware; `read-before-write-contract.md` is the SSOT for the mandate). Two rules previously mis-gated as Viindoo - the always-invisible-field XML comment (v18+) and the `hr.employee` field-groups requirement (v16+) - are reclassified as Odoo CORE (test-enforced) and made reachable for all profiles; only the short-form/no-bump version policy and `old_technical_name` remain Viindoo-gated. New `snippets/xml-view-conventions.md` (#117).
- `odoo-deep-survey` digs to the root instead of stopping at the directly-touched modules (issue #117 follow-on): it walks the dependency closure from the nearest modules down to `base` (phased, one layer per wave), maps the tests that protect the surveyed scope (own-module + base/dependency tests + the framework-validation/lint gates `base.TestInvisibleField` / `hr.TestSelfAccessProfile` / `test_pylint` / `test_lint`, flagged as not-OSM-indexed), and surfaces prior art (`find_examples` / `suggest_pattern`) so downstream design/code agents reuse instead of reinventing. Adds entry-point, data-flow, layer, side-effect and tech-debt lenses, reinforces OSM-first grounding, and keeps `SKILL.md` lean (detail in `references/survey-lenses.md` + `references/synthesis-schema.md`) (#117).
- `odoo-code-review` now auto-runs UI review for view changes and partitions large reviews (issue #117 follow-on). `odoo-review-scoper` classifies each module's changed files and returns a per-module `needs_ui_review` flag (any view-layer change, or a Python field/method the OSM confirms is view-bound) plus the affected screens; the per-module reviewer runs `UI_REVIEW=delegated` (non-rendered + view-source correctness only) and a new Phase A.5 dispatches `odoo-ui-reviewer` on the affected screens when an instance is reachable (else DONE_WITH_CONCERNS, never a hard block) - on both the single- and multi-module paths. When the change is too large for one opus, synthesis partitions by business domain (one opus per domain -> `domain-<d>.md`, then a final cross-domain opus -> `_synthesis.md`). Every phase persists its artifact under `.odoo-ai/reviews/<slug>-<date>/` (#117).

### Fixed

- `scripts/verify-backend.sh` lint gate parity: prepend `--disable=all` so only the derived Viindoo whitelist runs (no OCA-default broad enables), strip `#`-commented lines before deriving enabled codes, downgrade `unknown-option-value` (W0012) version drift to a non-blocking WARN, and fail-closed (loud WARN, never a silent green) when the whitelist cannot be derived; per-series `pylint_odoo` pins in `scripts/lib/odoo-python-matrix.json`; protected by `tests/test_verify_backend_gate.py` (red-before-green). The P5 install gate now runs framework validation with demo data ON (Runbot parity), and `odoo-deprecation-audit` scans at the TARGET version against the module's own source (with `era-reference.md` rewritten as a v8-v19 range). A performance lens (a stored compute aggregating a relation on a high-volume model must use a grouped `_read_group`) and verification discipline (no APPROVE-via-simulation; pre-write value / recompute claims require runtime evidence) were added to `odoo-code-reviewer` and `odoo-solution-architect`; `odoo-instance-ops` demo-flag guidance corrected to the v8-v18 vs v19 split (#117).
- Coder model-tier no longer leaves large work on sonnet: the `odoo-coding` §5 tier table now escalates a single-stack work-item to opus on size/scope (net-new-or-changed >=~200 LOC, >=~5 files, or a large / high-blast-radius target module), the sonnet catch-all is capped below those thresholds (#117).
- Mandatory guideline-read enforcement, to stop agents shipping stale version constructs (e.g. `<tree>` on v18 where the guideline says `<list>`) when they skip the guidelines or lose them to context compaction. `read-before-write-contract.md` (SSOT) and every code/debug/review/architect agent now carry a unified `MANDATORY HARD RULE` (no line of a file type written before its By-task-mapped guideline + pivot section is read), a just-in-time pivot-row re-read immediately before writing each file type, and a `VERSION RULES APPLIED` sticky-note the coder emits before code and the reviewer verifies (mismatch = HIGH) so the rules survive compaction; coder/frontend-coder/reviewer gain a hard `MANDATORY READ GATE` checklist item (locked in by `tests/test_execute_agent_hardening.py`). Stale duplicated version-facts in agent/reference prose (`@odoo-module` "v16-v17", `@api.multi` "v13/v14", the tree/list history note, frozen era tables) are purged in favour of `odoo-version-pivots.md` pointers (#117).

## [3.27.0] - 2026-06-25

### Added

- Added `snippets/test-expected-log-contract.md` (SSOT): the expected-log contract for tests that legitimately emit a server/console WARNING/ERROR - an `assertLogs`-vs-`mute_logger` decision rule plus a 3-layer matrix (Python log / SQL constraint / JS-OWL), with the JS framework era split (v17 QUnit vs v18+ Hoot) resolved at runtime via `js_test_inspect` rather than hardcoded. Wired as a pointer (rule body stays in the snippet) into the coder/reviewer/debugger triad with distinct duties - coder wraps, reviewer flags a missing wrapper as HIGH, debugger treats a matching WARNING as expected noise: `odoo-test-writing`, `odoo-coder`, `odoo-frontend-coder`, `odoo-code-reviewer`, `odoo-debug`, `odoo-backend-debugger`, and `docs/reference/ODOO-TESTING.md` (#114).

### Fixed

- Fixed `scripts/verify-frontend.sh` reporting a false-green `PASS` for the JS lint gate. It now resolves `eslint`/`prettier` from the repo-pinned `node_modules/.bin` (git-worktree aware, with an `npx --no-install` last resort; global `command -v` resolution removed), runs the real Runbot oracle `eslint --no-eslintrc -c _eslintrc.json --resolve-plugins-relative-to MAIN_ROOT` (replacing standalone `prettier --check`) with a prettier version-pin pre-check, and emits a tri-state result - `PASS` (exit 0) / `FAIL` (exit 1) / `CANNOT-VERIFY` (exit 2). An unresolved toolchain or a v14 no-gate layout now emits `CANNOT-VERIFY` (a soft-stop the agent must not treat as a pass), never `PASS`. Consumer agents/skills/docs updated to honor `CANNOT-VERIFY` = not-clean (#112).

## [3.26.0] - 2026-06-25

### Added

- Added greenfield `__manifest__.py` authoring guidance (scaffold-first, preserve scaffold commented placeholders, short non-series-prefixed `version`) as a dedicated snippet (`new-module-manifest.md`) wired into `odoo-coder` (directive + checklist) and `odoo-code-reviewer` (MED convention finding); `odoo-frontend-coder` references it at the manifest-wiring step; `odoo-coding` skill brief updated.
- Added profile-gated module-rename guidance (`snippets/module-rename.md`): under a Viindoo Standard/Internal profile (OSM-detected), a renamed module's manifest must carry `old_technical_name` (Viindoo-internal tooling key, ignored by Odoo core loader, additive to OpenUpgrade DB-level rename); wired into `odoo-coder` (directive + checklist item) and `odoo-code-reviewer` (MED finding, explicitly non-applicable outside Viindoo distributions).

## [3.24.0] - 2026-06-22

## [3.23.0] - 2026-06-22

### Added

- **Universal Work Ethos auto-loaded into every agent.** A new `ODOO-AI-ETHOS.md` at the plugin
  root holds 11 cross-cutting work principles (completeness, root-cause analysis, SSOT,
  behavior-protecting tests, ASCII-hyphen output, and so on). A SessionStart hook
  (`ensure-ethos-import.sh`) idempotently writes a sentinel-bounded absolute `@import` of it into
  the user's global `~/.claude/CLAUDE.md`, so the principles load into the main agent and every
  custom sub-agent (built-in Plan/Explore agents skip CLAUDE.md by design). The hook is
  corruption-safe and self-healing, creates CLAUDE.md if missing, and preserves a symlinked
  CLAUDE.md. Opt out with `ODOO_AI_NO_ETHOS_IMPORT=1`; the principles then apply across all your
  Claude Code projects, not only Odoo work.

## [3.22.0] - 2026-06-22

### Fixed

- **`/odoo-setup` verifies Odoo by running `odoo-bin --version`, not `python -c "import odoo"`.**
  A source-only Odoo checkout is never pip-installed, so the old bare-import gate
  (`45-venv.sh`, `50-instance-spinup.sh`) false-negatived a healthy venv and refused to record
  the instance's `python` field; it also misread Odoo 19's namespace package as broken. The gate
  now runs the real entrypoint - which self-inserts its repo on `sys.path` - and fails loud when
  the core repo is absent, instead of editable-installing Odoo. (#104)
- **`/odoo-setup` AI-4 venv probe is v8-v19 safe and principle-based.** Series detection now runs
  `odoo-bin --version` / `import odoo.release` instead of inspecting `import odoo` /
  `site-packages/odoo` (a false-negative on namespace-package Odoo 19), and escalates an
  `unknown` result to the user instead of guessing. (#104)

### Added

- **Per-profile venv and instance recording.** `[[instance]]` blocks gain optional `profile` /
  `instance_key`; `45-venv.sh create-venv --profile <name>` builds an isolated
  `venvs/<series>-<profile>` venv and verifies every repo in the profile is present before
  recording the interpreter. `40-instance-profile.sh`, `50-instance-spinup.sh`,
  `instances_io.py`, and `allocator.py` (`--profile`) carry the profile through, so two profiles
  of the same series no longer collide on venv path, DB name, or instance identity. (#104)

## [3.21.0] - 2026-06-21

### Changed

- feat(odoo-ai-agents): forward-port pipeline reorder - intent-extract + 4-outcome classify + a conditional design step now run BEFORE the plan gate, so the plan is built from understood intent (not bucket guesses). New order: P0 recon (no stop) -> P1 intent extract -> P2 classify + installable-probe -> P3 design (conditional route-out) -> P4 plan gate -> P5 merge -> P6 symbol-survival -> P7 drift -> P8 adapt -> P9 verify -> P10 gate-merge -> P11 PR
- feat(odoo-ai-agents): forward-port plan gate moved into harness Plan Mode (EnterPlanMode / ExitPlanMode); plan.md is now a resume record, not the approval gate
- feat(odoo-ai-agents): odoo-intake skips its own Plan Mode when routing to odoo-forward-port (forward-port owns its P4 gate - no double Plan Mode)

### Added

- feat(odoo-ai-agents): installable:False category-3 - a module first made-installable at the source series but not yet upgraded for the target lands installable:False, decided by a TARGET CLEAN-TIP (pre-merge) discriminator
- feat(odoo-ai-agents): new read-only agent odoo-installable-prober - reads target clean-tip manifest + source git-history to drive the category-3 installable decision (delegated heavy git-history read)
- feat(odoo-ai-agents): conditional design route-out to odoo-solution-design for complex (bucket-(c)) modules via a return_to round-trip (design-only; returns to forward-port without dispatching a coder)

## [3.20.1] - 2026-06-21

- fix(odoo-ai-agents): odoo-doc-illustrator real-module smoke fixes - never drop existing on-disk doc locales (language list = tier-resolved UNION disk-detected locales, so a module already shipping bilingual docs keeps all of them); derive odoo_version from the parent dir series when the manifest version does not encode an Odoo series (Viindoo-style `0.2.2`); convention-detect now also scans `doc/` for bilingual RST

## [3.20.0] - 2026-06-21

- feat(odoo-ai-agents): new odoo-doc-illustrator agent - browser-driven visual documentation (capture screenshots into module static/description or cluster docs)
- feat(odoo-ai-agents): new odoo-doc-illustration thin skill dispatching odoo-doc-illustrator
- feat(odoo-ai-agents): wire odoo-doc-illustration into odoo-intake routing + collision-zones, and into odoo-content-draft / odoo-onboarding / odoo-capability-proof / odoo-feature-highlights continuation contracts
- feat(odoo-ai-agents): odoo-doc-illustrator real-module workflow - DOC LAYER appstore|userguide|both (App Store index.html + doc/index.rst), multilingual docs resolved from i18n.json default_languages, convention-detect from the target module, crop-default capture, [Hinh anh:] marker shared with odoo-content-draft

## [3.19.1] - 2026-06-21

### Fixed

- **Dropped non-portable `/code-review` and `/skill-creator` references.** These slash commands
  exist only on the maintainer's machine, so the `odoo-forward-port` pipeline that called
  them would fail for any other user of this public plugin. Odoo code review now routes to the
  bundled `odoo-code-review` skill (OSM-grounded, always available, auto-spawns its reviewer from the
  orchestrating context); both commands are removed from the WI-worker spawner-ban enumerations and
  the maintainer notes.
- **`odoo-intake` Phase R no longer mislabels read-only leaf skills as Agent-tool targets.**
  `odoo-feature-check` / `odoo-override-finding` are skills (not agentTypes), so they are invoked via
  the Skill tool; only `Explore` / anonymous recon agents are launched directly - resolving the
  contradiction with the skill's own dispatch-mechanism rule.

### Changed

- **Neutral subagent-launch language.** Now that nested subagents are supported, skills describe
  dispatching a specialist agent as "launch ... as a subagent" rather than prescribing "the Agent
  tool", letting the execute-agent choose the mechanism. Load-bearing technical facts (a skill name
  is not an agentType, so it must go through the Skill tool) are kept.

## [3.19.0] - 2026-06-21

### Fixed

- **forward-port P4.5 now scans production code, not only `tests/`.** The python-import and
  AST-pyflakes survival classes run over ALL merged-touched `.py` (production AND `tests/`), so a
  runtime `NameError` left in production code by a clean merge is caught statically before the slow
  P5 behavioral run instead of slipping through to a chance test path. (Closes #101)
- **forward-port P5 triages every red against a clean-tip baseline.** A red test - whether in an
  edited module or in a co-installed dependency pulled in by the install closure - must be proven
  against a clean target tip before it is called a regression; co-installed-dependency reds are
  almost always pre-existing.
- **odoo-code-review surfaces the lint gate in the verdict.** The `### Lint gate (pylint-odoo)` slot
  reports PASS / FAILED / SKIPPED; a soft-degraded (toolchain-absent) run reads SKIPPED and must not
  be reported as a clean Python pass - an unrun gate is not a green gate.
- **odoo-code-review Phase 0 detects a sibling git worktree.** When `WORKTREE_PATH` is supplied it
  diffs there (`git -C <path> diff`) instead of cwd, so changes living in an `odoo-forward-port`
  worktree are no longer silently reviewed as clean. `verify-backend.sh` gains `VERIFY_BACKEND_GIT_DIR`.
- **odoo-intake no longer double-gates a skill that owns a stronger gate.** When a routed skill opens
  with its own STOP plan gate (e.g. `odoo-forward-port` P0 per-commit plan), intake launches it
  directly instead of emitting a redundant soft-plan-gate.

### Added

- **forward-port symbol-survival class (g): ORM `create`/`write` dict-key field-literal scan.** Over
  all merged-touched `.py` (production call sites + test helpers), each dict key is cross-checked per
  field via `entity_lookup(kind='field')` to catch a renamed/removed field or a Many2one->Many2many
  type flip that pyflakes cannot see.
- **forward-port P5 optional `--test-tags` narrowing.** When the untagged closure suite is
  impractically large, the run may narrow to touched modules + their direct dependers - never to the
  edited module alone, which would hide a broken downstream-depender test.
- **odoo-onboarding persists a verify-environment cache** (`verify_python`, `addons_path`) into
  `.odoo-ai/context.md` so P5 / run / verify steps read it instead of re-discovering the interpreter
  and addons-path each time; the SSOT remains `~/.odoo-ai/instances.toml`.

## [3.18.0] - 2026-06-20

### Added

- **New `odoo-instance-ops` agent + `odoo-instance` skill** for end-to-end Odoo instance lifecycle
  (create, drop, init-modules, update-modules, run-tests, ensure-up, status) across all series v8+.
  Allocator B2 model: reserve-only acquire, Odoo create-on-init, through-Odoo drop via `odoo_db.py`
  and `55-instance-ops.sh`. Per-version CLI grounding via OSM `cli_help` with local-source fallback.
  Persistent logs at `${ODOO_AI_HOME:-$HOME/.odoo-ai}/logs/`; parseable output lines `LOG_PATH=`, `STATUS=`,
  `TEST_RESULT=` forwarded in the canonical `instance-ops` handoff block.

## [3.17.1] - 2026-06-20

### Added

- odoo-i18n: translate into a LIST of target languages in one run (default vi_VN) instead of a single hard-coded language. P0 resolves the language list by precedence (explicit args > ~/.odoo-ai/i18n.json default_languages > existing <lang>.po filenames > res.lang active=True > default vi_VN) and echoes the source before the approval STOP.
- odoo-i18n: add a machine-global language registry ~/.odoo-ai/i18n.json ({"default_languages":[...]}), seeded idempotently by the odoo-setup instance-profile step; documented in commands/odoo-setup.md and docs/setup.md.
- odoo-i18n: document a per-language loop order in the recipe (.pot exported once per module, language-agnostic; .po / glossary / validation per language) plus per-language artifact naming (glossary-tm-<lang>.json, translation-report-<lang>.json, consistency-audit-<lang>.md).
- odoo-i18n: fix the v19 i18n example filenames in the recipe so the export and import lines agree (-o and -w now both use <lang>.po).

## [3.17.0] - 2026-06-20

### Added

- **New `odoo-i18n` skill + `odoo-translator` agent (closes #76).** A dedicated spawner skill for
  Odoo translation work (`.pot`/`.po`) usable by any workflow - forward-port, new-module/feature
  development, bug-fix. Non-destructive recipe (SSOT `skills/odoo-i18n/references/i18n-recipe.md`):
  `polib` translation-memory merge (`po.merge(pot)`) that preserves existing `msgstr`, isolated-DB
  per-module export with `-i <module> --skip-auto-install` (Odoo >=17; isolated-DB-per-dependency-order
  for <17) to avoid auto-install noise, non-empty-`msgstr` regression via `polib` (not `grep`),
  placeholder-integrity check, and validation by Odoo `-u` reload (not `msgfmt`). Instance-mandatory
  (no no-DB workaround); consistency audit is advisory (safe for independent VN circular regimes).
- **`Terminology consistency` guidance** added to `coding_guidelines/{14..19}.0/python.md` - look up
  the canonical term (core+deps TM / `.odoo-ai/glossary.yml` / OSM `entity_lookup` field.string)
  before coining a new label.
- Invariant test gates `tests/test_forward_port_hardening.py` and `tests/test_odoo_i18n.py`.

### Changed

- **`odoo-forward-port` hardening (closes #90).** P3.5 symbol-survival now covers 6 auto-merge-silent
  blind-spots (test base-class signature drift, file-existence refs, dynamic `ref()`/xml_id, Python
  import survival, AST `pyflakes` scan, `installable`-flag transitions) and includes `tests/` files.
  New P4.5 pre-adapt drift scan with a "test files collect cleanly" acceptance gate. P5 verify adds
  `--skip-auto-install` + `--http-port`, per-module `Loading module` parse, transitive-deps breadth,
  and baseline-fail attribution. P7 review made mandatory for grafted engines (enumerate every code
  path, cross-check static-review bot, attribution diff vs `origin/<target>`). The destructive i18n
  re-export caveat is replaced by a dispatch to the new `odoo-i18n` skill. New `installable:False`
  lint-only lane (dormant modules get lint/syntax fixes only, no logic review). `odoo-coding` emits
  `SUGGESTED_NEXT: odoo-i18n` after new-module or translatable-string work.

### Fixed

- `odoo-backend-debugger` / `_shared/debug-method.md`: a `0 failed, N error(s)` test result (setUpClass
  crash) is no longer read as a pass - tests did not run; never conclude "transient" without a
  deterministic red->green toggle.

## [3.16.2] - 2026-06-20

### Fixed

- `/odoo-plan-upgrade` now routes through `/odoo-intake` Phase P so the workflow's `on_complete`
  design handoff (`needs_design == true` -> `odoo-solution-design`) auto-advances under the run-driver
  instead of degrading to a human suggestion when the command is run directly. Closes #93.
- `check_workflows.py` driver-required warning is now sentinel-aware: a command declaring the
  `engages-run-driver` marker clears the warning, while a command that dispatches a driver-required
  (`on_complete`) workflow directly still trips it. Added `tests/test_check_workflows_driver.py`
  (red-green: sentinel-less command warns, sentinel command clears, plus a real-repo regression guard).

## [3.16.1] - 2026-06-20

### Changed

- Merged the forward-port pipeline into a single skill: `odoo-run-forward-port` is renamed
  to `odoo-forward-port` and absorbs the former command shim (argument schema, when-to-use,
  examples). `/odoo-forward-port` now invokes the skill directly.

### Removed

- The `odoo-forward-port` command shim (`commands/odoo-forward-port.md`); its `/odoo-forward-port`
  entry point is preserved by the renamed skill of the same name.

## [3.16.0] - 2026-06-20

### Changed

- **Relax the subagent-orchestration model to match Claude Code's multi-level nesting**
  (subagents may now spawn subagents, hard cap depth 5). The plugin no longer enforces a
  self-imposed "flat depth-1" model: removed every depth label (`depth0-only`,
  `depth-2 ceiling`, "never invoke from inside a subagent", "main-agent-only") across
  skills, agents, commands, docs, hooks and the generated orchestration map/digest.
- Subagent launching is now described generically as "launch subagent" instead of
  prescribing the `Agent tool` by name; the architectural `Skill tool` vs `Agent tool`
  dispatch distinction (skills are loaded via the Skill tool, raw agents via the Agent
  tool) is kept as accurate documentation.
- Repurpose `snippets/nesting-guard.md` -> `snippets/worker-brief.md`: drop the depth/
  nesting guard, keep the non-depth worker rails (OSM grounding + worktree git-isolation).

### Removed

- The `depth_policy` orchestration field (plus its `check_orchestration.py` validator,
  the generated `ORCHESTRATION-MAP.md` column and the digest line) - it was a duplicate
  of `spawn_class`.
- The `disallowedTools` spawn/skill locks (`Agent`, `Task`, `Skill`) on all 8 agent
  bundles - agents inherit the full tool surface and the harness depth cap is the only net.
- The flat-depth test guards that protected the retired model (`test_agent_frontmatter`
  Agent-in-disallowed assert, `test_agent_depth_rule_guard`, `test_agent_skill_invocation_guard`,
  `test_wi_brief_nesting_rule_present`); the principal-branch-lock and human-confirm-merge
  wave guards are kept.

### Fixed

- Ground the forward-port frontend adapt leg against `odoo-frontend-fidelity.md`
  (closes a pre-existing `orchestration-check` design-system gap).

## [3.15.0] - 2026-06-19

### Added

- **OSM test surface in the tool generator** - register the 6 test-writing tools from
  odoo-semantic-server PR #323 (`find_test_examples`, `tests_covering`,
  `test_class_inspect`, `test_base_classes`, `test_coverage_audit`, `js_test_inspect`)
  and the 2 test resources (`odoo://{version}/test/{module}/{class_name}`,
  `odoo://{version}/testcoverage/{model}`) into `generator/server-surface.json`
  (`server_version` 0.13.1 -> 0.15.0, 25 -> 31 tools, 7 -> 9 resources).
- Declare the test tools in `generator/skill_tool_deps.json` for the auto-gen skills
  `odoo-solution-design`, `odoo-run-forward-port`, `odoo-debug` and
  `odoo-deprecation-audit`, bumping their `min_server_version` to 0.15.0; regenerate the
  `## MCP tools` blocks, snippets and orchestration map via `make gen`.

### Changed

- `suggest_pattern` gains an optional `category` parameter and `module_inspect` documents
  the `method='tests'` discriminator (metadata refresh from PR #323). The
  `module_inspect` description refresh propagates to every skill block that lists it.
- **Ground the test surface across the code/test skills and agents** - wire the OSM PR #323
  test tools into the existing grounding points so agents stop reinventing tests, picking
  the wrong base class, or emitting `cr.commit()` inside `TransactionCase`:
  - `odoo-test-writing`, `odoo-coding`, `odoo-qa-suite` - base-class selection via
    `test_base_classes` (carries the `cr.commit()` FORBIDDEN contract), coverage baseline
    via `tests_covering`/`test_coverage_audit`, test-only search via `find_test_examples`,
    helper inspection via `test_class_inspect`.
  - `odoo-coder`, `odoo-frontend-coder` - coverage pre-check before dispatching the
    test-author; a JS Test Grounding mini-protocol (`js_test_inspect` framework detection
    plus `find_test_examples` with `kind='js'`).
  - `odoo-code-review`, `odoo-debug`, `odoo-code-reviewer`, `odoo-backend-debugger` -
    evidence-ground the "missing test" finding and the regression-test spec instead of
    guessing; flag `cr.commit()` inside test code.
  - `odoo-solution-design`, `odoo-solution-architect` - §7 test strategy grounded in OSM.
  - `odoo-run-forward-port` - P3.5 test-survival check so a test referencing a symbol
    deleted on the target version is caught instead of silently auto-merged.
  - `odoo-deep-survey` maps test
    blast-radius; `odoo-intent-extractor` grounds test-class base chains;
    `odoo-deprecation-audit` detects deprecated test APIs (`SavepointCase`, QUnit -> Hoot).
- Wiring corrected against live OSM behavior: `find_test_examples` kind enum is
  `transaction|http|form|js` (no `python`); `SavepointCase` is a deprecated alias still
  present in v16+ (not a removal); `test_class_inspect` returns base chain + cursor
  contract, not setUpClass fixture contents; `test_coverage_audit` reports field-level gaps
  only; JS is QUnit on v17 and Hoot on v18+.
- `suggest_pattern(category='test')` is intentionally NOT wired: the server returns empty
  (test patterns not yet seeded) - tracked as a follow-up issue against odoo-semantic-server.

## [3.14.2] - 2026-06-19

### Added

- **Example-tool-call required-param gate** (`tests/test_agent_facing_guidance.py`) - new
  `test_example_tool_calls_pass_all_required_params` asserts every concrete example tool call in
  `skills/`, `agents/`, `snippets/`, `docs/` supplies ALL required params per
  `generator/server-surface.json` (not just valid param names). Uses slot-based positional coverage
  (a param is satisfied when named or when a positional fills its slot in the tool's canonical
  `example_call`), so tools that interleave an optional positional between required ones
  (`entity_lookup`, `profile_inspect`, `lint_check`, `cli_help`) are handled correctly. Ellipsis
  sketches (`...`/`…`) stay exempt. Closes the gap where an example missing a required param
  (e.g. `model_inspect` without `method=`) passed CI but was rejected by the OSM server at runtime.
- **Kind-conditional required-param gate** (`tests/test_agent_facing_guidance.py`) - new
  `test_example_tool_calls_pass_conditional_required_params` enforces `entity_lookup`'s kind-dispatched
  discriminators (ADR-0028): `kind='field'` needs `model=`+`field=`, `kind='method'` needs
  `model=`+`method_name=`, `kind='view'` needs `xmlid=`, `kind='module'`/`'pattern'` needs `name=`. Rules
  are data-driven from a new `conditional_required` map in `generator/server-surface.json`. Catches the
  class where an example is gate-clean on universal required params but uses the wrong/absent kind
  discriminator (e.g. `entity_lookup(kind='field', name=...)`), which the OSM server rejects at runtime.
  Pipe-alternation (`kind='a'|'b'`), placeholders, and `...` sketches are skipped/exempt.

### Fixed

- **21 example tool calls missing a required param** across 13 files - added the missing discriminator
  (`module_inspect` -> `name=`, `model_inspect` -> `model=`/`method=`) so copied examples are
  runtime-valid. Doc-only (examples in skills/agents/snippets/docs prose); no runtime behavior change.
- **`entity_lookup` kind-conditional discriminator examples** - fixed `entity_lookup(kind='field', ...,
  name=...)` -> `field=...` (OSM rejects `name=` for `kind='field'`) and converted illustrative/
  comparison-prose `entity_lookup(kind='method'/'field'/'view', ...)` shorthands to `...` sketches.
- **`lint_check` surface drift** (`generator/server-surface.json`) - moved `code` from `optional_params`
  to `required_params` to match the live OSM schema (`code` is required); regenerated the Cursor/OpenAI/
  Gemini tool-surface snippets accordingly. Strengthens the required-param gate for `lint_check`.

## [3.14.1] - 2026-06-19

### Added

- **Security Pitfalls coding-guideline doc** (`skills/_shared/coding_guidelines/<ver>/security.md`)
  for every supported series 14.0-19.0 - the secure-coding companion to `python.md`, extracted
  from the official Odoo `security.rst#security-pitfalls` (v14 from `reference/addons/`, v15-19
  from `reference/backend/`). Covers Unsafe Public Methods, Bypassing the ORM / SQL injection,
  domain injection (`Domain`, v19), Unescaped field content / `t-raw` XSS, `markupsafe.Markup`
  (v17+), Escaping vs Sanitizing, Evaluating content / `safe_eval`, and Accessing object
  attributes / `getattr`. Each file is self-contained per the per-version convention.

### Changed

- The six per-version `python.md` warnings that pointed at a non-existent "Security Pitfalls
  (reference/security/pitfalls)" section now resolve to the local `security.md` in the same
  directory - closing a 6-way dangling reference.
- `security.md` is wired into the mandatory read-before-write set: the Round-1 topic-file
  enumeration of `odoo-coder`, `odoo-frontend-coder`, `odoo-code-reviewer`, and
  `odoo-solution-architect`, the backend list in `snippets/read-before-write-contract.md`, and
  the "Table of contents" + "By task" rows of every `coding_guidelines/<ver>/INDEX.md`.

### Fixed

- Replaced the dangling `scripts/verify-guidelines.sh` reference (a script that never existed)
  in `coding_guidelines/INDEX.md` and `snippets/read-before-write-contract.md` with the real
  pre-push gates `scripts/verify-backend.sh` and `scripts/verify-frontend.sh`.
- Corrected upstream bugs in the v19 "Bypassing the ORM" code example (`x[x]` -> `x[0]`, added
  the missing closing bracket) carried into `19.0/security.md`, annotated inline.

### Tests

- `tests/test_execute_agent_hardening.py` gains a "B4" section asserting each `security.md`
  exists with a `# Security Pitfalls` heading, each `python.md` warning resolves locally (no
  `reference/security/pitfalls`), the four code agents + the contract snippet name `security.md`,
  the new docs are ASCII-hyphen-only, and `verify-guidelines.sh` is gone.

## [3.14.0] - 2026-06-18

### Added

- **`/odoo-forward-port` command** (`commands/odoo-forward-port.md`) - thin shim for
  continuous and one-shot forward-port workflows; accepts `<source-ref> <target-branch>
  [--scope] [--since] [--one-shot]` and resume-checks `checkpoint.json` before dispatching
  to the `odoo-run-forward-port` skill orchestrator.
- **`odoo-intent-extractor` agent** (`agents/odoo-intent-extractor.md`) - read-only
  per-commit intent extraction used in Phase 1 of the forward-port pipeline; model is
  `sonnet` by default with caller-level override at dispatch; `disallowedTools` blocks
  `Agent`, `Task`, and `Skill` to enforce the read-only contract.
- **`odoo-run-forward-port` skill** (`skills/odoo-run-forward-port/SKILL.md`) - 8-phase
  forward-port orchestrator (SSOT): P0 plan-gate, P1 parallel intent-extract, P2
  4-outcome classify, P3 merge --no-commit, P3.5 symbol-survival-check (autosilent-break
  gate), P4 test-first adapt (serial per commit), P5 per-batch verify, P6 merge-gate,
  P7 PR + review. Merge-keep-SHA protocol: outcome (a)/(d) commits merge without adapt
  diff; worktree isolation throughout.
- **Snippet `fp-intent-4outcome`** (`snippets/fp-intent-4outcome.md`) - SSOT 4-outcome
  classification table for forward-port commits (skip / 3-way+adapt / re-implement /
  skip-new-module).
- **Snippet `fp-symbol-survival-check`** (`snippets/fp-symbol-survival-check.md`) - SSOT
  Phase 3.5 autosilent-break gate: OSM-ground every symbol on the source side of
  conflicted + merge-clean-but-source-touched files; symbol absent in target forces bucket
  b/c/d, blocking silent field-break absorption.
- **Snippet `fp-merge-absorption`** (`snippets/fp-merge-absorption.md`) - merge-keep-SHA
  protocol and per-batch verify toggle; codifies the skip-code-still-merges rule (outcome
  a/d) and the RED-then-GREEN confirm-by-toggle gate for FP-delta tests.
- **Snippet `fp-installable-false`** (`snippets/fp-installable-false.md`) - new-module
  forward-port handling: set `installable: False`, comment out `auto_install` and
  `application`, run only lint; tracks the migration-rename gate
  (`installed < parse(dir)`).

### Changed

- **`odoo-test-writing`** gains a new `adapt` mode for forward-port test forwarding:
  translates API calls to the target version, strips source-snapshot assertions, and
  confirms RED-on-target before handing back to the adapt phase. Reference detail in
  `skills/odoo-test-writing/references/fp-adapt-mode.md`.
- **`odoo-version-diff`** gains a reference to the FP 4-outcome mapping
  (`snippets/fp-intent-4outcome.md`) so version-diff callers can bucket findings
  consistently with the forward-port pipeline.
- **`odoo-code-review`** gains pitfall #11 (test-coupled-to-src-API): flag tests that
  hard-code source-version field names or method signatures as HIGH when reviewing
  forward-ported code.
- **`snippets/test-first-contract`** gains a forward-port RED-on-target paragraph:
  a test that passes without modification on the target branch is not a forwarded test,
  it is a tautology - confirm RED before adapting.

## [3.13.0] - 2026-06-18

### Added

- **Concurrent Odoo instance allocator** (`plugins/odoo-ai-agents/scripts/lib/allocator.py`) - a
  deterministic, version-agnostic lease allocator so many subagents across many concurrent Claude
  Code sessions stop colliding on the single declared `db_name`/`http_port`. Each caller gets either
  an isolated **ephemeral** database (auto `createdb` on acquire, `dropdb` + filestore cleanup on
  release/GC; degrades to exclusive when the DB role lacks `CREATEDB`), an **exclusive** lease on the
  declared instance (single holder + pooled ports), or a lease-free **readonly** handle.
  Coordination is an atomic RMW under an `fcntl.flock`-guarded registry at
  `${ODOO_AI_HOME:-$HOME/.odoo-ai}/runtime/`; stale leases are reclaimed opportunistically at each
  acquire (dead-pid same-host + TTL). The allocator returns resource facts only (db, ports, token);
  consumers build the `odoo-bin` command and map ports to CLI flags via `cli_help` at runtime, so
  future Odoo CLI changes never touch the script. Subcommands `acquire`/`release`/`heartbeat`/`gc`/
  `list` emit shell-eval `ALLOC_*` lines. Design: `docs/reference/INSTANCE-ALLOCATION.md`; 12
  behavior tests in `tests/test_allocator.py` (the Postgres `createdb`/`dropdb` path skips when no
  local PG). Wired into the backend/frontend coders (DB-touching `odoo-bin` runs acquire an ephemeral
  DB, then release), the resolution snippets (`instance-resolution.md` "Allocate, don't just
  resolve"; `resolve_instances.sh` `_odoo_ai_runtime_dir` SSOT; `venv-resolution.md`),
  `skills/_shared/concurrency-guard.md`, `skills/odoo-coding/SKILL.md`, and
  `docs/reference/ODOO-TESTING.md`.
- **Shared live-render target wired into the allocator** - a new non-exclusive `shared` mode plus a
  `query --series` discovery subcommand let `scripts/setup-steps/50-instance-spinup.sh` register the
  spun-up server (its actual bound port + the live server pid; `created_db=false` so gc never drops
  the declared DB) and let `snippets/instance-resolution.md` discover that live port across sessions
  before falling back to the static `http_port`. The four visual consumers (`odoo-ui-reviewer` /
  `odoo-ui-debugger` / `odoo-visual-regression` / `odoo-demo-recording`) inherit it through the
  resolution snippet with no per-consumer edits; registration is best-effort and degrades to plain
  spin-up when the allocator is absent. A concurrent same-series start is benign (the loser loses the
  OS port bind and both sessions attach to the one live server).

### Changed

- **Engineering agents hardened and compacted** (`odoo-coder`, `odoo-solution-architect`,
  `odoo-frontend-coder`, `odoo-code-reviewer`). New normative guidance - Domain Knowledge
  Activation, Module Ownership / dependency-direction integrity (incl. the CE/EE bug-fixes-only
  policy), Code Quality Standards (flake8 / ESLint as functional requirements), solution/module
  Acceptance Criteria, and a per-module-vs-synthesis review mode - while the preloaded
  system-prompt token cost was reduced by tightening prose (agent bodies are rewrite-only, so no
  relocation). `odoo-coder`'s `disallowedTools` was narrowed to block only `Agent`, so it can invoke
  the `odoo-test-writing` skill for the test-first loop. `odoo-ui-debugger` / `odoo-ui-reviewer`
  gained a "headless by default, headed only on request" browser-mode section.
- **`odoo-code-reviewer` now reviews intent + domain + TDD conformance, and is compacted 299 -> 183
  lines.** It gained a Domain Knowledge Activation section, an intent / business-value lens, and a
  TDD-conformance step: when the dispatch brief carries `DESIGN_DOC: <path>` (wired through
  `skills/odoo-code-review`), the reviewer verifies the code against the design's Intent & Business
  Value (section 1) and Acceptance Criteria (section 9, solution + per-module) and emits a
  `### TDD Conformance` block - an unmet criterion or a code-vs-intent divergence is a HIGH/CRITICAL
  finding.
- **No more hardcoded `17.0` version default.** Across agents, personas, skills and snippets the
  example tool-calls now use a `<version>` placeholder, and the agents STOP and ask when the target
  Odoo version is ambiguous instead of silently assuming v17.
- **`odoo-coding` dispatch brief slimmed to run-specific params only** - the per-module procedure is
  stated once in the agent system prompt (SSOT). `tests/test_execute_agent_hardening.py` was
  repurposed from a brief-snapshot assert to a behavior assert.
- **Repo-wide ASCII-hyphen normalization** (em-/en-dash -> `-`) across docs, skills, agents,
  snippets, workflows and tests.

### Fixed

- **Profile-name correction** `viindoo_internal_17` -> `standard_viindoo_17` in
  `generator/server-surface.json`, `hooks/detect-intent.sh`, `docs/reference/workflow-harness.md`
  and several skills/snippets.
- **Skill-name consistency** `odoo-test-writer` -> `odoo-test-writing` (skill directory rename plus
  all references in docs, agents, skills, snippets and tests).

## [3.12.0] - 2026-06-16

### Added

- **`/odoo-setup` runs an interactive checkbox menu when given no arguments** -
  `plugins/odoo-ai-agents/commands/odoo-setup.md`. You no longer need to remember any flag: type
  `/odoo-setup` and pick what to do from an `AskUserQuestion` multi-select (browser automation stack /
  declare + spin up a local instance / reset `instances.toml`). The filter arguments
  (`all`/`browser`/`runtime`/`permissions`/`instance`/`--reset`) remain as optional shortcuts.
- **New setup step `47-instance-reset.sh`** - backs up `instances.toml` then writes a clean file,
  dropping dead/legacy entries; `--hard` wipes all instances. Reset-only (`--reset` filter); its
  `check` is always-satisfied so the `all` loop never triggers it.
- **New library `scripts/lib/osm_repo_map.py`** - normalizes any git remote URL (SCP/SSH/HTTPS) to a
  single match key and builds SSH clone commands (`-b <branch> --no-single-branch`, `odoo<major>` dir).

### Changed

- **The `/odoo-setup` instance cluster is now OSM-grounded and propose-then-confirm** instead of
  auto-deciding. It asks the Odoo Semantic index for versions -> profiles -> repos, spawns a read-only
  scan to map each repo/venv to a local path, and confirms every mapping with the user before any file
  is written (5 confirm gates). When the index is unavailable it degrades to a user-declared mode.
  `addons_path` ordering is own-repos-first -> ancestor -> core-last (Odoo resolves modules
  first-wins), reorderable at the confirm gate. The hard rule "do not spawn a subagent" is replaced by
  "spawn a read-only scan only; all file mutations go through the deterministic step scripts".
- **Setup step `40-instance-profile.sh` no longer auto-discovers-and-writes.** `apply` requires a
  confirmed `ODOO_AI_PROFILE_SPEC` (validated upfront - no partial writes) and refuses to write
  without it.
- **Setup steps `45-venv.sh` / `50-instance-spinup.sh` hardened.** `45` records the `python` field only
  after `import odoo` succeeds and accepts multiple `--requirements`; `50` validates the interpreter
  and database reachability before launch and fails loudly instead of polling a doomed start.

## [3.11.5] - 2026-06-16

### Changed

- **`instances.toml` is now machine-global, resolvable from any working directory**
  (`plugins/odoo-ai-agents/scripts/lib/resolve_instances.sh`). Previously the setup steps wrote and
  read `<cwd>/.odoo-ai/instances.toml`, so an execute-agent running in a different repo could not
  discover an Odoo instance declared elsewhere - yet the declared instances are a property of the
  HOST, not the project. The instance profile now lives at the machine-global
  `~/.odoo-ai/instances.toml` (override with `ODOO_AI_HOME`, or an explicit full-path
  `ODOO_AI_INSTANCES`). Resolution is global-wins: `$ODOO_AI_INSTANCES` ->
  `${ODOO_AI_HOME:-$HOME/.odoo-ai}/instances.toml` -> a project-local `./.odoo-ai/instances.toml`
  (transitional fallback). Steps `40`/`45`/`50` share the new resolver; `40 apply` migrates an
  existing project-local file to the global path once (idempotent copy, never clobbers) and writes a
  defensive `~/.odoo-ai/.gitignore`. Every other `.odoo-ai/` artifact (`context.md`, `survey/`,
  `worklog/`, ...) stays project-scoped. The resolver is bash 3.2-safe (macOS) and covered by new
  tests in `tests/test_setup_instances.py`. Agent/skill/doc guidance updated; see the new
  `plugins/odoo-ai-agents/snippets/instance-resolution.md`.
- **Agents that RUN Odoo now have an interpreter-discovery pointer** - new
  `plugins/odoo-ai-agents/snippets/venv-resolution.md` documents how to resolve the venv `python`
  to run `odoo-bin` (scaffold / `--test-enable`) / tests / migrations: the matching instance's
  `python` field (via `instances_io.py read`) -> `$ODOO_PYTHON` -> system `python3` (last resort),
  the same chain `50-instance-spinup.sh` uses. Wired into `odoo-coding` (the `odoo-bin scaffold`
  step), `odoo-test-writing`, and `odoo-data-migration`. Also finishes the instance-resolution wiring
  in `odoo-demo-recording` (it now falls back to the machine-global `instances.toml` instead of
  immediately asking the human).

## [3.11.4] - 2026-06-16

### Fixed

- **Playwright browser deps now install correctly across the supported Ubuntu LTS line
  (22.04 / 24.04 / 26.04) and macOS 13+** (`plugins/odoo-ai-agents/scripts/setup-steps/20-browser-deps.sh`).
  Playwright is now pinned via `PLAYWRIGHT_PIN` (default `1.61.0`, the first release that supports
  Ubuntu 26.04 per microsoft/playwright#40117, and still valid on 22.04/24.04 and macOS). The
  previous unpinned `npx -y playwright install` resolved to whatever the local npx cache held (e.g.
  1.60.0), which cannot install Chromium on Ubuntu 26.04. The pinned Chromium build is shared by the
  `pagecast` server, so this covers pagecast too. A new CI matrix
  (`.github/workflows/validate.yml` -> `browser-deps`) runs the real install plus a headless
  Chromium launch on ubuntu-22.04, ubuntu-24.04, ubuntu-26.04 (public preview), and every macOS
  version GitHub still hosts a runner for - macos-14 / macos-15 / macos-26 (arm64) plus
  macos-15-intel (x86_64). (macos-13 is not used: GitHub retired that runner image on 2025-12-08,
  so any job pinned to it queues forever; the binary-only macOS path still works on macOS 13+.)

### Changed

- `20-browser-deps.sh apply` now also installs Chromium's shared system libraries on apt-based
  Linux: automatically via `playwright install-deps` when passwordless `sudo` is available,
  otherwise it prints the exact command to run (it never runs sudo silently). `check` now probes
  those libraries by real soname, so a host that has the browser binary cached but the libraries
  missing is correctly reported as not-ready instead of being skipped. macOS, Windows, and non-apt
  Linux keep the binary-only path unchanged.

## [3.11.3] - 2026-06-14

### Fixed

- **Killed the recurring `undefined is not an object (evaluating 'modules')` crash** that hit the main
  agent whenever it dispatched `odoo-coding` (and, by imitation, other tasks) through the Claude Code
  Workflow (JS) tool. Root cause: `odoo-coding/SKILL.md` shipped a JS Workflow script that destructured
  the `args` global with no guard, no invocation example, and a resume example that omitted `args` -
  so `args` arrived `undefined` (passed as a JSON string, omitted, or dropped on resume) and the script
  crashed on the first `args` access. The Workflow tool always needs a JS script and `args` is
  `undefined` when not provided, so the fragile path was removed rather than patched.

### Changed

- **`odoo-coding` now dispatches the coder agents via the Agent tool exclusively, in model-weighted
  batches** (SSOT `skills/_shared/concurrency-guard.md` Mode B), instead of a JS Workflow pipeline.
  Test-author isolation is
  preserved (two sequential Agent calls - no JS needed). Trade-off accepted: true rolling-window becomes
  a model-weighted batch barrier per round, and `resumeFromRunId` is gone (resume = re-dispatch the
  BLOCKED modules as fresh Agent calls).
- `docs/reference/workflow-harness.md`: added an invariant - this plugin does NOT use the Claude Code
  Workflow (JS) tool; all fan-out is Agent-tool / Skill-tool / `run-driver`. README, ORCHESTRATION-MAP
  (regenerated from `generator/skill_tool_deps.json`), `concurrency-guard.md`, and `wave/SKILL.md`
  updated to match.

### Removed

- The inline JS Workflow script and all "Workflow tool / rolling-window pipeline" dispatch guidance from
  `odoo-coding/SKILL.md` (~376 net lines). `tests/test_concurrency_guard_ssot.py`:
  `test_odoo_coding_passes_model_explicitly_on_both_paths` -> `test_odoo_coding_passes_model_explicitly`
  (a single dispatch path now).

## [3.11.2] - 2026-06-14

### Changed

- **Agents now get the FULL odoo-semantic surface, drift-proof.** Every `agents/*.md` drops its
  enumerated `mcp__odoo-semantic__*` `tools:` allowlist and instead omits `tools:` (inherit the full
  tool surface dynamically) + a minimal `disallowedTools` denylist. When the OSM server adds/renames a
  tool, agents pick it up automatically - no `server-surface.json` snapshot edit, no PR, no drift. The
  enumerated allowlist could never track the live server (the snapshot is hand-maintained), so this
  replaces it with dynamic inheritance. `disallowedTools` blocks only spawn (`Agent`/`Task`) on every
  agent, plus `Skill` on the 5 agents that must not invoke skills (kept for `odoo-frontend-coder` /
  `odoo-solution-architect`, which invoke `odoo-frontend-design`). Write/Edit are NOT blocked - every
  agent writes artifacts (worklog/report/design-doc/source).
- **Fixed a latent bug:** `odoo-backend-debugger`, `odoo-ui-debugger`, `odoo-ui-reviewer` instructed
  "APPEND your worklog" but lacked `Write` in their allowlist (could not actually write). Inheriting the
  full surface restores `Write`, so the worklog contract now works.
- **`odoo-code-reviewer`:** replaced the hard-coded 11-tool step-by-step OSM usage list with a general
  directive ("you have the full surface - pick whatever fits, no fixed tool list"); review logic,
  severity rules, and snippet wiring unchanged. Stale "tool allowlist above" guard prose in all agents
  updated (there is no allowlist anymore).
- `generator/skill_tool_deps.json`: dropped the vestigial `agents:` section (agents inherit, not
  enumerated). Tests updated to the new agent contract (`disallowedTools` carries the no-spawn guard;
  OSM is inherited).

## [3.11.1] - 2026-06-14

### Changed

- **Compressed all 41 SKILL.md bodies + 7 agent system-prompts to cut token-per-invoke.** Structure
  refactor (no behavior change): reference-only blocks (worked examples, output-format templates,
  lookup tables, the brl Phase-E deliverable templates, the wave Mode-B dispatch loop) were relocated
  to per-skill `references/` files behind a one-line `${CLAUDE_PLUGIN_ROOT}/...` pointer (progressive
  disclosure - loaded on demand, not every invocation), and verbose prose was tightened. Agents are
  rewrite-only (their body is a preloaded system prompt, so no relocation). Skill bodies -25.0%
  (645,872 -> 484,526 B), agent bodies -16.6% (160,026 -> 133,507 B); ~188 KB removed from the
  on-invoke load. Frontmatter/descriptions byte-identical (triggering unchanged); all generated tool
  blocks untouched; full `pytest tests/` green.
- **`odoo-intake`: added a "Your role - orchestrator, not implementer" section** at the top of the
  body - frames the main agent as the team leader that gets work done by invoking the right skill
  (Skill tool), launching an agent directly only when no skill fits, and owning orchestration +
  decisions rather than hand-implementing.

## [3.11.0] - 2026-06-13

### Added

- **`hooks/auto-approve-browser.sh` (PermissionRequest hook).** Auto-approves the plugin's own
  browser MCP tools in-session, closing the window where SessionStart-applied permissions only take
  effect after a restart (Claude Code finalizes permissions before SessionStart fires). Stays silent
  (pass-through) for any non-plugin tool; opt out with `ODOO_AI_NO_AUTO_PERMS=1`.
- **`scripts/bump-version.sh auto` + `make bump` / `make bump-dry`.** Deterministic version-bump
  classifier that makes the existing policy operational: a `feat:` commit or a newly added
  command/skill/agent file -> minor; fix/refactor/docs/chore -> patch; `type!:` or `BREAKING CHANGE:`
  footer -> major. A human may still name an explicit `X.Y.Z` (natural-language override). The commit
  range anchors on the last `VERSION` change, not the (stale) `v*` tags.

### Fixed

- **Browser MCP `-headed` tools no longer prompt on every call.** The permission allow-list is now
  DERIVED from `.mcp.json` (the single source of truth) and lists every server - all three `-headed`
  variants included - fixing a drift where only the 3 base servers were allow-listed. A permission
  rule `mcp__<server>` matches at the `mcp__<server>__` boundary, so it never covered the distinct
  `-headed` servers; each needs its own entry.

## [3.10.0] - 2026-06-13

### Added

- **Two-variant browser MCP servers (headless default + headed on request).** Each browser backend
  (chrome-devtools, playwright, pagecast) now ships TWO servers: a headless default (`<name>`, passes
  `--headless`) and a visible `<name>-headed` variant - 6 servers total. The AI agent selects the
  `-headed` variant only when the human asks to watch the browser; the choice is which tool it calls
  (NL/AI-driven), NOT an env var or on-disk flag. chrome-devtools + playwright also pass `--isolated`
  so concurrent Claude/Codex/Gemini sessions get a private profile (fixes the "browser already
  running, use --isolated" collision); the headless default makes the visual stack work on
  no-display/CI hosts out of the box.
- **`hooks/ensure-browser-permissions.sh` (SessionStart).** Self-applies the browser MCP tool
  permission prefixes to `~/.claude/settings.json` on every session (idempotent; no-op once present),
  so the visual-UI agents run without a per-tool approval prompt after any install/update. Opt out
  with `ODOO_AI_NO_AUTO_PERMS=1`.

### Changed

- **`odoo-ui-reviewer` / `odoo-ui-debugger` are now self-contained**: they grant the plugin's OWN
  browser prefix (`mcp__plugin_odoo-ai-agents_chrome-devtools__*`) plus its `-headed` variant,
  dropping the implicit dependency on the standalone `chrome-devtools-mcp` plugin. Both default to the
  headless variant and switch to `-headed` only when the dispatch brief carries `BROWSER MODE: headed`.
- **`30-permissions.sh`** allow-lists the plugin-namespaced own prefixes
  (`mcp__plugin_odoo-ai-agents_{chrome-devtools,playwright,pagecast}`), which match both the headless
  and `-headed` variants.

## [3.9.0] - (unreleased)

### Added

- **New opt-in `odoo-deep-survey` skill**: a read-only, multi-phase survey (broad haiku sweep ->
  narrow sonnet dives -> optional opus pass) that `odoo-intake` offers on large / open-ended jobs.
  When the user approves `deep-survey`, it writes a synthesis under `.odoo-ai/survey/` that
  re-informs a sharper Proposed Plan before any code is written (read-only; spawner-agent,
  depth0-only). Skill count 40 -> 41.
- **Two new grounding-contract SSOT snippets** loaded by reference (edit once, not per agent):
  `snippets/read-before-write-contract.md` (read the target version's coding guidelines BEFORE
  writing code and conform on the first pass, not patched against a checklist afterward) and
  `snippets/test-behavior-contract.md` (tests drive the REAL workflow via
  `action_confirm`/`button_validate`/`Form()`/`with_user()` and assert observable outcomes, never
  seeding the terminal state with `create({'state': ...})`).

### Changed

- **`odoo-intake` resolves the Odoo version up front**: it escalates to `odoo-onboarding` to pick
  version/profile when the version is unknown and OSM is reachable (inline-menu fallback), or asks
  for the version + repo path when OSM is down - making the recon and plan context-aware.
- **`odoo-intake` fast-paths review / PR-review and debug intents**: these route straight to
  `odoo-code-review` / `odoo-debug` with no Proposed-Plan block and no Plan Mode.
- **Autonomous fix loop**: on a CRITICAL/HIGH finding, `odoo-code-review` / `odoo-debug` now drive
  the fix on their own through `odoo-coding` and re-review to verify (review -> code -> review),
  bounded to 3 rounds then escalates.
- **Agent identity priming**: each agent is primed with its own identity at the start of its run.
- **Plugin-wide removal of private-vault citations**: the ETHOS and Iron-Law references that named
  a private vault are renamed to in-plugin concept names - Anti-rationalize gate, Root-cause-first
  rule, and Pre-wave gate - so the public plugin is self-contained.
- **Skill-conflict resolution consolidated**: the `odoo-coding` legacy-JS-vs-OWL paradigm rule
  (previously §4.4 of the routing matrix) now lives in the generated
  `docs/reference/ORCHESTRATION-MAP.md`, which also points to
  `skills/odoo-intake/references/collision-zones.md` for the full collision policy.

### Removed

- **`docs/reference/mcp-tool-routing.md` deleted** (was 437 lines, generator-managed): the
  static-vs-live guidance it carried is already injected by the MCP server and duplicated in every
  skill's `## MCP tools` block + the IDE snippets, and its tool/persona/param tables duplicated the
  live `tools/list` schema and per-agent tool whitelists. `gen_surface.py` no longer emits it.
- **Execute-agent noise stripped from skill bodies**: the `_Tool surface: server vX._` version stamp
  (28 skill `## MCP tools` blocks, both generated and manual) and the `## Notes for future
  maintainers` roadmap subsection in `odoo-onboarding` carried no signal for an executing agent and
  were removed. The IDE-adapter snippets keep their stamp (they target non-Claude clients).

## [3.8.0] - 2026-06-12

### Added

- **Execute-agent hardening across the design -> code -> review -> debug chain** (#68): six SSOT
  contracts that the relevant agents now load by reference (edit once, not per agent) -
  `snippets/worklog-contract.md` (append-only cross-agent decision log under
  `.odoo-ai/worklog/<run>/`), `snippets/odoo-platform-design-principles.md` (multi-company + branch
  v17+, generic-before-localization, standard app-menu shape), `snippets/bidirectional-impact.md`
  (upstream + downstream impact, direct + indirect), `snippets/demo-data-dynamic.md` (time-relative
  `relativedelta` demo data), `snippets/test-first-contract.md` (red-before-green), and
  `skills/_shared/odoo-module-graph.md` (the shared Odoo module DAG). The five coder / reviewer /
  debugger agents that lacked it gain the `mcp__odoo-semantic__impact_analysis` tool.
- **Test-first loop in `odoo-coding`**: a separate test-author writes a failing test before the
  code for non-trivial modules (the coder self-tests for trivial ones), feeding a bounded
  `code -> review+test -> code` loop; `odoo-code-review` gates test coverage and loops fixes back to
  `odoo-coding` / `odoo-test-writing`.
- **Module-aware wave batching**: Phase 0 computes the Odoo module DAG, auto-infers work-item `depends_on`
  from module dependencies, and warns on work-items that cross module boundaries.

### Changed

- `odoo-solution-architect` now surveys bidirectional impact, designs dynamic demo data, and checks
  the three platform design principles. The README gains a "Grounding contracts" table, and the
  ChatGPT / Gemini / Cursor instruction ports gain a self-contained Odoo Design Principles block.

### Fixed

- **`odoo-solution-architect` could ship designs that violated coding conventions and named
  non-existent fields / methods**, which every downstream coder then built on. It now reads the
  target version's `coding_guidelines/` like the coders do, and a HARD RULE separates EXISTING
  entities (must be OSM- or disk-verified, never named from memory) from PROPOSED additions (may be
  new, but follow naming conventions and are marked in the data-model / override tables).

## [3.7.0] - 2026-06-11

### Changed

- **Plugin renamed `odoo-semantic-skills` -> `odoo-ai-agents`** (display name "Odoo AI Agent Team"):
  end users should uninstall the old plugin and install the new one -
  `/plugin uninstall odoo-semantic-skills@viindoo-plugins` then
  `/plugin install odoo-ai-agents@viindoo-plugins`. The `odoo-semantic` MCP server and the
  `odoo-semantic-mcp` sibling plugin are **unchanged** - `mcp__odoo-semantic__*` tool references
  continue to work without modification.
- **Skill renamed `intake` -> `odoo-intake`**: the Odoo-specific front door now carries the
  standard `odoo-` prefix, consistent with every other Odoo skill. The bare `intake` namespace is
  reserved for a future domain-agnostic front door that may invoke `odoo-intake` when it detects
  Odoo intent. Update any `/intake` references to `/odoo-intake`.

## [3.6.0] - 2026-06-11

### Changed

- **wave Phase 2 rolling-window (Mode B) + fable escalation** (`odoo-semantic-skills`, #61):
  Wave Phase 2 migrates from cap-3 Agent-tool batching to the Mode B model-weighted budget
  (BUDGET=8, per `skills/_shared/concurrency-guard.md`); cherry-pick stays a serialized depth-0
  critical section and a dependent WI starts only after its dependency is cherry-picked
  (`cherry_picked[dep]` gate, dependent worktrees created lazily). `odoo-debug` Phase 2 and the
  wave end-of-wave review gain a **fable** escalation tier (human-confirm + automatic opus
  fallback) - fable fires only after an inconclusive opus pass, or for a large wave review
  (changed lines > ~1500 or N >= 8 WIs).
  - Deferred: the YAML `model_tier: fable` enum is intentionally NOT added (no consumer needs it;
    CI rejects it loudly). When the first consumer appears, change three places in one commit:
    `generator/check_workflows.py`, `tests/test_workflow_format.py`, `workflows/_schema.md`.

### Fixed

- **Docs/skills synced to server fixes** (`odoo-semantic-skills`, #62): `lint_check` guidance now
  describes the V0.5 hybrid matcher (deterministic `[pattern]` on security-rule classes like
  sql-injection, heuristic `[fuzzy]` elsewhere) instead of the old "fuzzy V0 / can miss SQL
  injection" framing - while keeping "hint, not the gate" (`verify-backend.sh` + `/test_lint`
  remain authoritative). ORM-tool timeout prose is softened to reflect the server-side query
  bound (the client `"timeout": 90000` is now a defensive backstop, not the sole protection).
  `resolve_orm_chain` documents depth-first inherited-field resolution.

## [3.5.0] - 2026-06-10

### Added

- **Rolling-window codegen dispatch + per-work-item model tiers** (`odoo-semantic-skills`,
  closes #59): `odoo-coding` replaces the fixed "fire 3, wait, fire 3" Agent-tool batching
  with a canonical **Workflow-tool pipeline** (per-module backend->frontend stages, dependency
  promises instead of wave barriers, plain-JS weighted semaphore) plus an Agent-tool
  weighted-batch fallback when the Workflow tool is unavailable. Phase 0 gains a deterministic
  4-tier model table (haiku / sonnet / opus / **fable**, sonnet default) sourced from the
  design-doc effort tier or file/LOC/override heuristics; the gate table and `plan.md` now
  record an explicit `model` per work-item, and every dispatch passes `model` explicitly
  (agent frontmatter is a floor only, mirroring `odoo-debug`).
- **Concurrency-guard SSOT** (`skills/_shared/concurrency-guard.md`): the OOM fan-out rule
  now lives in one place - Mode A (legacy cap-3 batching) and Mode B (model-weighted budget:
  haiku=1, sonnet=2, opus=4, fable=8; budget 8). The four fan-out skills (`odoo-coding`,
  `odoo-debug`, `odoo-code-review`, `workflow-chaining`) reference it instead of
  restating the numbers. Guarded by `tests/test_concurrency_guard_ssot.py`.
- **Claude Fable 5 integration** (`claude-fable-5`, tier above opus, 2x opus price):
  row 1 of the `odoo-coding` tier table (Custom-XL / >=3-module full-stack work, never a
  default, design-doc-first), and `odoo-solution-design` now passes an explicit
  `model: opus|fable` per dispatch (fable only for Custom-XL designs).
- **Coder agents** (`odoo-coder`, `odoo-frontend-coder`): documented the model
  floor/override convention and the shared-version invariant for concurrent runs;
  frontend-coder gains a Read-the-SKILL fallback for `odoo-frontend-design` when the Skill
  tool is unavailable under the Workflow harness.

## [3.4.1] - 2026-06-09

## [3.4.0] - 2026-06-08

### Added

- **Solution-design phase** (`odoo-semantic-skills`): new skill `odoo-solution-design` + agent
  `odoo-solution-architect` (opus, full read-only OSM surface) that turn a classified
  requirement / upgrade / migration / refactor goal into a gate-able Technical Design Document
  under `.odoo-ai/designs/` before any code is written, with a **human design-approval gate** that
  runs before Plan Mode (`design → approve → Plan Mode → code → review`). Wired into intake
  routing + the design-first rule, the `odoo-brl` / `odoo-data-migration` handoffs, and the
  `odoo-implement-feature` + `odoo-plan-upgrade` workflows.
- **`odoo-frontend-design`** skill: leaf, knowledge-only (no agent spawn) design-quality
  expertise that `odoo-solution-design` and `odoo-coding` load via the Skill tool, and the bar
  `odoo-ui-review` rates against.
- **`odoo-coding`** skill: the single full-stack coding front door (see Changed/Removed). Scopes
  the target module set, computes dependency order via OSM, and dispatches the backend then
  frontend coder agents in waves (≤3 concurrent) via the Agent tool, building to an approved
  design doc when present.

### Changed

- **`odoo-code-review` scaled to multi-module**: one module → single sonnet reviewer; many →
  per-module fan-out (≤3 concurrent) + an opus integration pass over the full dependency closure
  (forward via `module_inspect`, reverse via `impact_analysis`). Output persisted under
  `.odoo-ai/reviews/`.
- **`intake` slimmed via progressive disclosure** (793 → 551 lines): collision zones, Plan Mode
  schema, Phase P RUN-DAG, and maintainer notes moved to `skills/intake/references/`, loaded on
  demand; routing table + gating hot path kept inline.
- **Skill-tool invocation phrasing locked** to `` invoke skill `<name>` using skill tool ``.

### Removed

- **`odoo-backend-coding`** and **`odoo-frontend-coding`** skills - subsumed by the unified
  `odoo-coding` front door (the `odoo-coder` / `odoo-frontend-coder` agents are retained as its
  companions). Net skill count 39 → 40; agents 6 → 7.

## [3.3.0] - 2026-06-08

### Added

- **Per-version Odoo coding-guidelines SSOT** under
  `skills/_shared/coding_guidelines/<version>/` (14.0 through 19.0). Each version directory is
  self-contained (no cross-version deltas) and split into topic files
  (`module-structure`, `python`, `naming`, `model-ordering`, `xml`, `javascript`, `scss`) with a
  per-version `INDEX.md` and a root index. Content is extracted faithfully from the official
  `coding_guidelines.rst` of each branch.
- **Read-before-write wiring** in the engineering agents (`odoo-coder`, `odoo-code-reviewer`,
  `odoo-frontend-coder`, `odoo-backend-debugger`, `odoo-ui-debugger`) plus the three engineering
  SKILL.md briefs: after the Odoo version is resolved, the agent MUST read the matching
  `coding_guidelines/<version>/` files BEFORE writing code (correct on the first pass, not a
  post-hoc checklist). The reviewer cites the violated guideline by version file + section.

### Changed

- `hooks/enforce-grounding.sh` adds a non-blocking note when a subagent writes backend Python
  without reading a `coding_guidelines/<version>/` file (read-before-write reminder). Consistent
  with the plugin's "notes, not blocks, for non-provable gaps" philosophy.
- `generator/check_orchestration.py` now verifies the coding-guidelines root + per-version index
  files exist on disk (ref-target integrity).

## [3.2.0] - 2026-06-08

### Added

- **`odoo-debug` front-door skill** + two specialist agents (`odoo-backend-debugger`,
  `odoo-ui-debugger`). Routes a debugging request to the right specialist instead of forcing
  the caller to pick. This release also bumps the version so marketplace clients holding a
  cached `3.1.0` re-pull and actually receive the new skill/agents (they were invisible while
  the version string stayed put).

### Fixed

- `odoo-semantic-skills` manifest `description` (and the Codex `longDescription` + generated
  Gemini extension) said "28 skill personas" - a stale count. Corrected to "39 skills" to match
  the actual skill set and the README canon (39 skills + 4 agents + 9 commands).

## [3.1.0] - 2026-06-07

### Added

- **Plan-once, Drive-to-done orchestration.** `/intake` plans a multi-step job once, then
  `run-driver` (a depth-0 loop) drives it to `DONE` / `BLOCKED` / `NEEDS_CONTEXT` via a
  machine-readable Continuation Contract and an `.odoo-ai/run-<id>.json` blackboard. Adds an
  autonomy dial (`--auto` default / `--step` / `--plan`) and gate tiers L0/L1/L2 (L2 always
  stops for a human; the dial can never lower it), plus cross-workflow `on_complete`
  transitions. Three advisory hooks (`remind-delegate`, `drive-continuation`,
  `parse-continuation`) nudge but never hard-block the main agent.
- **7 new domain skills:** `odoo-test-writing`, `odoo-security-audit`, `odoo-data-migration`,
  `odoo-perf-audit`, `odoo-pricing-proposal`, `odoo-rfp-response`, `odoo-customer-health`.
- **`research-multiphase` workflow** - flexible-phase, multi-model-tier research dogfood.

### Changed

- **Per-plugin READMEs.** Split the shared root README into self-contained
  `odoo-semantic-skills` and `odoo-semantic-mcp` READMEs; the root README is now a monorepo
  landing page that links to both. Reworked the overview/commands mermaid diagrams for
  readability (vertical layout, fewer crossing edges).

## [3.0.0] - 2026-06-06

### Changed (BREAKING) - naming normalization across skills, agents, and commands

Names now encode **role** so an AI router (and a human) can tell the three layers apart even
when a name appears bare, without its `odoo-semantic-skills:` namespace: **skill** = a
capability noun (`-review`, `-analysis`, `-coding`), **agent** = an actor noun (`-er/-or`),
**command** = an imperative verb-object (`odoo-run-brl`). This removes three skill↔agent
name collisions and the agent-suffixed skills that were masquerading as executors. The full
convention is documented in `CONTRIBUTING.md` → "Naming convention: skill vs agent vs command".

**Migration (clean break, no aliases).** There is **no backward-compatibility shim** - invoking
an old name after updating to 3.0.0 fails with "not found"; use the new name (table below). To
defer migration, pin the plugin to `2.x`. The four **agent** names are unchanged. Skill
descriptions/trigger phrases are unchanged, so natural-language routing behaves identically -
only explicit slash commands and bare name references changed.

**Skills renamed (10):**

| Old | New |
|-----|-----|
| `odoo-coder` | `odoo-backend-coding` |
| `odoo-code-reviewer` | `odoo-code-review` |
| `odoo-ui-reviewer` | `odoo-ui-review` |
| `odoo-demo-recorder` | `odoo-demo-recording` |
| `odoo-objection-handler` | `odoo-objection-handling` |
| `odoo-override-finder` | `odoo-override-finding` |
| `odoo-discovery-summarize` | `odoo-discovery-summary` |
| `odoo-onboard` | `odoo-onboarding` |
| `odoo-ui-debug` | `odoo-ui-debugging` |
| `workflow-runner` | `workflow-chaining` |

**Commands renamed (9)** - `name:` now equals the filename (the invoked name); old `name:`
fields that never matched their file are corrected:

| Old command | New command |
|-------------|-------------|
| `/odoo-bid-respond` | `/odoo-respond-bid` |
| `/odoo-customer-followup-draft` | `/odoo-draft-followup` |
| `/odoo-discovery-quick` | `/odoo-summarize-discovery` |
| `/odoo-feature-positioning` | `/odoo-position-feature` |
| `/odoo-upgrade-plan-full` | `/odoo-plan-upgrade` |
| `/odoo-brl-run` | `/odoo-run-brl` |
| `/odoo-video-produce` | `/odoo-produce-video` |
| `/setup` | `/odoo-setup` |

The 4 agents (`odoo-coder`, `odoo-code-reviewer`, `odoo-ui-reviewer`, `odoo-frontend-coder`)
keep their names. SSOT `generator/skill_tool_deps.json`, the orchestration map, workflow files,
manifests, and docs were updated in lockstep; `make gen` output is regenerated.

## [2.8.0] - 2026-06-06

### Added

- **Local reproduction of the Odoo code-quality CI gate (issue #46) - multi-version aware, baked
  into the verify/test flow.** New `scripts/verify-backend.sh` is the backend sibling of
  `verify-frontend.sh`: it runs `pylint --load-plugins=pylint_odoo` on changed Python from an
  **isolated tools venv** (`$ODOO_AI_DIR/tools/pylint-<series>/`, never the instance venv), with
  pylint/astroid/pylint-odoo pinned per Odoo series in the extended
  `scripts/lib/odoo-python-matrix.json` (`lint` block; 16/17 → the verified-faithful
  pylint-odoo 8.0.22 · pylint 2.15.10 · astroid 2.13.5 combo, 18 → 9.x (pylint 3), 19 → 10.x
  (pylint 4, which pylint-odoo 10 hard-requires) - each pylint era-matched to its pylint-odoo major
  to avoid checker-plugin crashes). Always loads `pylint_odoo` so the
  `consider-merging-classes-inherited` pragma never reads as the `W0012` vanilla false signal, and
  **derives the enabled-code set from the deployment's own quality module** (`test_pylint`/`test_lint`)
  when present - no deployment-internal config is vendored. Graceful degradation (soft-warn, exit 0)
  when the toolchain/series/files are absent, with an opt-in `--provision` to build the pinned venv.
  Shipped fallback `scripts/odoo-pylintrc` (OCA defaults).
- **`/test_lint` mandate in the test-run SSOT.** `docs/reference/ODOO-TESTING.md` now documents the
  two-part gate (core `test_lint` + `pylint-odoo`) once; `odoo-qa-suite`, `odoo-deploy-checklist`,
  `INSTANCE-LIFECYCLE.md` and `osm-first-contract.md` inherit it via their existing pointers.
  `odoo-coder` (Round 4) and `odoo-code-reviewer` now run `verify-backend.sh`; `odoo-deploy-checklist`
  gains a Domain-6 pre-push parity item. New reference: `docs/reference/odoo-code-quality.md`.
- **Enforcement substrate - `SubagentStop` grounding hook (`hooks/enforce-grounding.sh`).** Turns the
  previously advisory OSM-first contract into a checkable invariant: it reads the worker's own
  transcript (assistant-authored content only) and **blocks once** (loop-safe via `stop_hook_active`)
  when an artifact claims `grounded: osm` but made zero `mcp__odoo-semantic__*` calls, asking the
  agent to actually verify or relabel honestly. Self-gates to Odoo-shaped subagents. Two softer
  gaps raise a **non-blocking note** (never a block - a block there only manufactures unverifiable
  `grounded: local-source` labels and false-blocks legit pure-Python/standalone work): backend
  code written with OSM reachable but the ORM validators skipped; and the **silent-skipper** -
  backend `.py` written with zero OSM calls and no grounding label at all (previously slipped
  through unnoticed). The `odoo-coder` Round-4 "skipped with reason noted" free bypass was
  tightened to require the standalone `grounded: local-source` label. Hook behavior is locked by
  `tests/test_enforce_grounding.py` (block / both notes / self-gate / honest-label / loop-guard).
- **Brand-agnostic brand-fidelity mechanism (no brand vendored).** Optional, consumer-driven via a
  new `brand_tokens_source` key in `.odoo-ai/context.md` (a JSON `token -> color` map). New
  `scripts/lib/color_delta.py` (stdlib CIEDE2000); `verify-frontend.sh` Tier 4 WARNs on hardcoded
  SCSS hex within ΔE of a declared brand token, and `odoo-ui-reviewer` Step 4b ΔE-diffs
  `getComputedStyle(:root)` against the map at runtime. Documented as Section G of
  `skills/_shared/odoo-frontend-fidelity.md`; mirrors the gate's "derive from the consumer
  environment, vendor nothing" principle so the public plugin stays brand-neutral.

## [2.7.1] - 2026-06-05

### Fixed

- **`detect-intent.sh` routed structure-lookup questions to the vault instead of the OSM index** -
  the UserPromptSubmit hook only surfaced the index hint for code-gen intents (domain
  `engineering|upgrade|visual-UI`) and worded it as "before generating or editing Odoo code", so a
  composition/lookup question ("which modules / repos does profile X contain") got no pointer to the
  index and the agent fell back to the vault - even though `profile_inspect` answers it directly.
  Added an `_is_lookup` intent probe (EN `module/repo/profile/version/inventory/composition` + VI
  `gồm / có gì / module nào / repo nào / những gì / có bao nhiêu`) that emits an `[OSM-lookup]` hint
  naming `profile_inspect` / `describe_module` / `model_inspect`, fired on Odoo/Viindoo anchor +
  lookup intent **independent of `_domain`** (so a general-domain Viindoo question still routes to
  the index). The hint is an in-context pointer that survives ToolSearch deferral of those tools.

## [2.7.0] - 2026-06-05

### Added

- **OSM server 0.13.1 surface sync (24 → 25 tools)** - mirror the new `profile_inspect` tool
  (`method=summary|repos|modules`: profile inheritance chain + repos + module inventory/count,
  ADR-0028) into `generator/server-surface.json` and wire it into the skills that answer
  "what's in this profile" questions: `odoo-onboard` (records module inventory into
  `.odoo-ai/context.md`), `odoo-customization-inventory`, `odoo-addon-diff`, `odoo-brl`,
  `odoo-risk-overview`, `odoo-competitive-brief`, `odoo-discovery-summarize`, `odoo-campaign-plan`.
- **Live version-gate (closes #40 Finding 2)** - `check_deps.py` now enforces the previously-dead
  `server_version_required` / per-skill `min_server_version` fields: each floor must cover the
  newest tool the skill/agent uses and stay ≤ the mirrored server version (semver compare).
- **OSM-maximization pass across skills + agents** - wired, at each phase, the OSM tool/resource
  that removes a concrete guessing step: `impact_analysis` (BRL Extension-M/L blast radius);
  `set_active_version` pins (ui-debug / visual-regression / demo-recorder / ui-reviewer - stop
  `odoo_version='auto'` resolving to latest-indexed); `module_inspect` scope numbers
  (feature-highlights / capability-proof / objection-handler / gap-analysis); `find_deprecated_usage`
  + `module_inspect(dependencies)` (customization-inventory upgrade-risk); `lookup_core_api` /
  `find_examples` / `api_version_diff` (override-finder); `set_active_profile` scoping
  (deprecation-audit); `cli_help` (deploy-checklist / qa-suite); `find_examples` (version-diff);
  agent tools `find_override_point` / `module_inspect` (coder), `entity_lookup` (frontend-coder),
  `find_examples` / `api_version_diff` / `find_style_override` / `resolve_stylesheet` (code-reviewer),
  `set_active_version` / `api_version_diff` (ui-reviewer). Added `odoo://` resource shortcuts where
  the entity id is already known.

### Fixed

- **#41 - skill examples pinned non-existent profile names** - replaced `viindoo-internal` (hyphen)
  and bare `odoo` with versioned names (`standard_viindoo_17`, `odoo_17`) across odoo-brl,
  odoo-gap-analysis, odoo-onboard, odoo-customization-inventory, odoo-addon-diff, evals, schema,
  workflow-harness, context-bootstrap; preserved the "read from `.odoo-ai/context.md` /
  `list_available_profiles`, never hard-code" guidance.
- **Tool descriptions resynced to 0.13.x behaviour** - `find_examples` documents the lexical
  fallback when the embedder is down (#264); `model_inspect` documents the `extenders` method +
  the real page caps (#262).

### Changed

- **Provenance stamp 0.11.1 → 0.13.1 (closes #40)** - `server_version` in the surface SSOT plus
  every hand-maintained "24 tools / v0.11.1" label (README, ROADMAP, setup.md, dev.md, snippet
  intros, MANUAL skill footers); generated surfaces regenerated via `make gen`.

## [2.6.0] - 2026-06-05

### Added

- **Agent-first grounding SSOT (PR #42)** - two new snippets the skills/agents reference by
  path: `snippets/disk-fallback-protocol.md` (three-tier grounding: OSM index → disk self-serve
  via Read/Grep/Bash/WebFetch → training-memory flagged `ungrounded`) and
  `snippets/context-bootstrap.md` (a mandatory Round 0 that reads `.odoo-ai/context.md` before
  asking the caller for version/profile/module list).
- **`odoo-frontend-coder` agent (PR #43)** - frontend coding is now an agent+skill bundle
  (mirrors `odoo-coder` / `odoo-code-reviewer`): a slim routing skill plus an isolated executor
  agent with a restricted tool allowlist (incl. `resolve_stylesheet` / `find_style_override`),
  so version-gating + multi-round MCP runs out of the main agent's context.

### Changed

- **Standalone-first fallback: paste-only → disk-grounded (PR #42)** - when OSM is unreachable
  a skill now reads the source itself (`find`/`grep`/`Read`, `WebFetch` upstream) instead of
  asking a human to paste code/fields/manifests; copy-pasteable output is the last resort
  (repo genuinely inaccessible). **This reverses the [2.5.0] decision to keep the fallback
  paste-only.** Visual skills return `BLOCKED(...)` when a browser/instance is unreachable
  rather than soliciting screenshots. `hooks/detect-intent.sh` recommends disk-grounded
  fallback accordingly.
- **Portability (PR #42)** - sales/visual flows no longer depend on the non-official live Odoo
  ERP MCP (`mcp__odoo__*`) or the claude.ai Gmail MCP; deal/CRM/email data comes from the
  invocation context and `.odoo-ai/context.md`, instance URL from `.odoo-ai/instances.toml`.
  Any live ERP/email integration is an optional bonus, never assumed.
- **Code skills self-author (PR #42)** - `odoo-coder` / `odoo-code-reviewer` /
  `odoo-frontend-coder` write and review code natively (boilerplate from `find_examples`
  templates, complex logic reasoned step by step, inline self-review) instead of delegating.
- **Model-tier (PR #42)** - `feature-positioning.workflow.yaml` feature-check / addon-diff
  `haiku` → `sonnet` (OSM synthesis, not simple lookup); `haiku` definition tightened in
  `_schema.md` / `workflow-harness.md` (never for write/synthesis phases). The
  `set_active_profile` example reads `viindoo_profile` from `.odoo-ai/context.md` instead of
  hard-coding `viindoo-internal`.
- **Frontend bundle + version portability (PR #43)** - the `odoo-frontend-coder` skill is
  renamed `odoo-frontend-coding` (the agent keeps the `odoo-frontend-coder` name); the
  wave / nesting-guard guidance is corrected so a depth-2 leaf worker never invokes a
  depth0-only bundle (it writes/reviews directly via OSM tools); hard-pinned `v8-v19` version
  ranges that only meant "all supported" are replaced with open phrasing ("any/all supported
  version", "v8+") while real era boundaries are kept; the README no longer tracks the plugin
  version.

### Removed

- **ollama-delegate (PR #42)** - removed all `mcp__ollama-delegate__*` delegation from the
  plugin and the `ollama_tools` field from every `generator/skill_tool_deps.json` entry (plus
  the `SKILL_OLLAMA_TOOLS` load and the "Ollama-delegate tools" render block in
  `generator/gen_surface.py`). The running agent generates/reviews code itself.

### Fixed

- **Session-pin scope wording (#253, follow-up to server #251/#252)** - corrected the
  `set_active_version` / `set_active_profile` sticky-context description from "per API key"
  to **per live MCP session** (single api-key/`_nosession` fallback for stdio/header-less,
  24h idle TTL, resets on server restart). Fixed at the SSOT
  (`generator/server-surface.json` tool description + `generator/gen_surface.py` legend) and
  regenerated via `make gen` (propagates to `mcp-tool-routing.md`, 12 SKILL.md, 3 snippets),
  plus the manual prose outside the generator (`docs/setup.md`, `docs/personas/dev.md`,
  `odoo-deploy-checklist`/`odoo-frontend-coder` SKILL.md, snippet intros, and the
  `odoo-brl` state-file `schema.md` re-bootstrap note). Prose-only - no tool-surface change
  (tool count stays 24), no client code change.

## [2.5.0] - 2026-06-03

### Added

- **Frontend fidelity (#37)** - make AI-authored Odoo OWL/JS + SCSS correct and lint-compliant
  by construction: an era-sectioned SSOT pitfall catalogue
  (`skills/_shared/odoo-frontend-fidelity.md`, v8-v19+), a write-time OWL grounding checklist
  plus a post-write verify gate (`scripts/verify-frontend.sh`, `scripts/rules/owl-pitfalls.txt`,
  `scripts/odoo-prettierrc.json`), and passing/broken `odoo-frontend-coder` examples.
- **Agent-facing guidance guard** (`tests/test_agent_facing_guidance.py`) - four checks keeping
  skills/snippets/agents/docs in sync with the server tool surface: no "omit/optional
  odoo_version" prose, no drifted parameter names, every named argument is a real parameter of
  its tool, and every example call to a version-required tool supplies `odoo_version`.

### Fixed

- Corrected AI-agent-facing tool guidance for the now-required `odoo_version`: removed
  "can omit / optional, default auto" prose, added `odoo_version='auto'` to ~166 example calls,
  and fixed drifted parameter names (`check_module_exists(module=)`→`name`,
  `find_deprecated_usage(scope=)` dropped, `lint_check(code_snippet=)`→`code`,
  `suggest_pattern(query=)`→`intent`, `lookup_core_api(symbol=)`→`name`,
  `api_version_diff(scope)`→`symbol`) across skills, the cursor/gemini/openai snippets, and
  agent definitions.
- **Tool-permission grants for file-authoring skills** - removed the `disallowed-tools: Write Edit`
  frontmatter block from the three skills whose own contract is to write deliverables to disk
  (`odoo-brl` → `.odoo-ai/brl/` rtm.csv/cost.json/dag/report.md, `odoo-qa-suite` →
  `.odoo-ai/qa/*.md`, `workflow-runner` → `output_dir` artifacts + checkpoints), which were previously blocked from delivering their output.
- Restored `odoo-coder` / `odoo-frontend-coder` to write/apply code directly (with a patch
  preview before applying), per the README's coder intent ("Coder - Write Odoo backend or
  frontend code", "fix writer … writes the override and shows a patch preview before
  applying") - undoing the v2.4.0 `disallowed-tools: Write Edit` drift that had reduced them
  to copy-paste-only. Removed the block from both skills, added `Write`/`Edit` to the
  `odoo-coder` agent's tool list, and reframed Phase 0 as a patch preview (not a write-block).
  The OSM-unreachable Standalone-first fallback stays paste-only.
- **AI-agent-consumer review follow-ups:**
  - Workflow-harness doc sync - `docs/reference/workflow-harness.md` no longer claims a
    platform-enforced `disallowed-tools: Write Edit` write-block (the gate is now behavioral
    Iron Law + Plan Mode; coders preview a patch then write). Updated the layer diagram,
    enforcement-stack table, and the mechanisms prose.
  - `set_active_version` 'auto'-needs-pin warning - clarified in `generator/server-surface.json`
    (the regeneration SSOT) that the tool needs a CONCRETE version (sentinels rejected), other
    calls reuse the pin via `odoo_version='auto'`, and `'auto'` is only safe AFTER a pin -
    without a pinned session it silently falls back to the latest indexed version. Regenerated
    all derived blocks.
  - Frontend gate hardening (`scripts/verify-frontend.sh` + `scripts/rules/owl-pitfalls.txt`):
    class-3 (`contenteditable`) now anchors on a quoted template attribute and only scans
    `.xml`/`.html`, so a JS CSS-selector string like `querySelector("[contenteditable=true]")`
    no longer hard-blocks; class-1 now also catches params-before-arrow (`(ev) => onSave(ev)`),
    PascalCase, and leading-underscore handlers while still ignoring `this.`/`props.` forms;
    portability fixes for macOS bash 3.2 (`mapfile`→read-loop, guarded empty-array expansion).
    Added a `class1_handlers.xml` fixture and a JS-selector case to the good fixture.
  - Agent-facing guard (`tests/test_agent_facing_guidance.py`) now matches the fully-qualified
    `mcp__<server>__tool(...)` call form (not just the bare name) and credits a positional
    toward `odoo_version` only when positionals reach its slot in the tool's canonical
    signature order - catching `suggest_pattern(...)`, `lint_check(code_chunk)`, and bare
    `cli_help(...)`/`lint_check(...)` calls that omitted the now-required version; fixed all
    the calls it newly caught.
  - Corrected the class-4 SCSS literal in `skills/_shared/odoo-frontend-fidelity.md` to the
    real Odoo source line `calc(#{map-get($spacers, 1 )} / 2)`
    (`calendar_renderer.scss:2`), replacing a fabricated `calc(#{map-get($spacers, 2)} * 2)`.

## [2.4.2] - 2026-06-02

### Build / CI

#### Added

- **`requirements.txt`** - single source of truth for test dependencies (`pytest` + `PyYAML`);
  previously undeclared, causing contributors to install deps ad-hoc and PyYAML-gated
  workflow tests to silently skip (~99 parametrized cases masked by the missing import).
- **`make setup`** - bootstraps `.venv` by probing for Python >= 3.12 (`python3.12` through
  `python`). All Makefile targets (`make test`, `make validate`, etc.) now run through
  `$(VENV)/bin/python` and auto-bootstrap the venv on first use if `make setup` was skipped.
- **Python 3.12+ prerequisite** documented in `README.md` (contributor section) and
  `CONTRIBUTING.md` (local development prerequisite).

#### Changed

- **CI `validate.yml` `schema` job** now runs `pip install -r requirements.txt` (was
  `pip install pytest`), ensuring PyYAML is present and the workflow-format test suite
  runs its full parametrized case set.

### odoo-semantic-skills

#### Changed

- Disambiguated the `odoo-semantic` name left over from the pre-split single
  plugin. Skill trigger phrases in `odoo-onboard` and `intake` now say
  `Odoo` (the onboarding skill bootstraps Odoo project context and installs no
  plugin), and standalone-fallback prose in `odoo-coder`, `odoo-code-reviewer`,
  `odoo-ui-reviewer`, `odoo-frontend-coder`, `odoo-onboard`, `upgrade-plan-full`,
  and `setup` now names `the odoo-semantic-mcp server` explicitly. Runtime
  identifiers (the MCP server id `odoo-semantic`, the `mcp__odoo-semantic__*`
  tool prefix, the brand `Odoo Semantic`, and the product URL) are unchanged.
- Compacted every specialist skill `description` under the 1024-character per-entry
  cap (28 skills; ~40,071 → ~27,051 chars, −32%). This eliminates skill-listing
  truncation - previously 28 descriptions exceeded the cap, forcing Claude to drop
  descriptions and degrade triggering. All `route to …` / `DO NOT trigger → …`
  disambiguation clauses, bilingual (EN+VN) triggers, version-resolution, and
  OSM-grounding signals are preserved; skill bodies, generated `## MCP tools` blocks,
  and output contracts are untouched. Validated against an isolated real-skill
  triggering eval (NEW vs OLD descriptions, flat aggregate). `intake` collision-zone
  guidance re-synced (`description matches` → `handles`).

#### Added

- `tests/test_skill_description_budget.py` (every skill description ≤ 1024 chars) and
  `tests/test_intake_quote_sync.py` (every skill/workflow the `intake` router names must
  exist) guardrails, locking in the description compaction above.
- `tests/test_naming_consistency.py` guardrail: fails if a bare `odoo-semantic`
  token reappears in the skill / command / trigger-phrase surface, allowlisting
  the server id, tool prefix, suffixed plugin names, and product URL.
- A naming-policy table in `CONTRIBUTING.md` documenting which form to use.
- A "First-time setup flow" table in `README.md` and `docs/setup.md` that
  distinguishes the three easily-confused setup steps: `/odoo-semantic-mcp:connect`
  (required, per machine), `/odoo-semantic-skills:setup` (optional visual stack,
  per machine), and the `odoo-onboard` skill (optional, per repo).

## [2.3.0] - 2026-05-31

### odoo-semantic-skills

#### Added

- **Git-wave orchestration** - depth-0 multi-subagent integration: integration branch +
  WI worktrees + cherry-pick + end-of-wave Opus review + PR + squash + tree-identity gate
  + human-confirm merge. Self-spawning, principal-branch-locked, auto-merge never allowed.
  Covers 1-WI minimal through ≥4-WI full plan-artifact (`.odoo-ai/wave/<slug>/plan.md`)
  with topology diagram and disjoint ownership map.

## [2.2.0] - 2026-05-31

### odoo-semantic-skills

#### Added

- **`intake` skill** - universal front door for all 9 persona buckets (CEO/strategist,
  consultant, sales AE, pre-sales, marketer, developer, QA, customer-success). Handles
  vague prompts via a 4-tier brainstorm-or-fast-path routing flow, proposes a plan gate
  before any execution skill fires, and is depth-0 only (never spawns subagents).
- **`odoo-brl` skill** - BRL engine for classifying and costing tens-to-thousands of
  business requirements: 4-way classification (CE/EE/Viindoo/Custom), deterministic cost
  lookup, dependency DAG with Kahn topological sort, and checkpoint/resume support for
  large jobs.
- **3 domain workflow YAMLs** - `bid-respond.workflow.yaml`, `discovery-pipeline.workflow.yaml`,
  and `feature-positioning.workflow.yaml` added as composition-runnable workflows using
  the `workflow-runner` skill as the execution harness.
- **Security hardening** - confidentiality guard expanded to cover 8 banned content groups
  across all skill/agent/command surface; intake hard-rule enforces depth-0 constraint.

#### Changed

- **Plugin command count corrected**: `commands` array now has 8 entries (added
  `odoo-brl-run.md` and `odoo-video-produce.md`); plugin.json description updated from
  "7 workflow commands" to "8 workflow commands".
- **Renamed `odoo-router` → `intake`**: the universal front-door skill was renamed for
  clarity; all cross-references updated.
- **VERSION bumped** from `2.1.0` to `2.2.0`, kept in sync with `plugin.json.version`.

## [2.1.0] - 2026-05-29

### Added
- **Visual UI testing stack** for the `odoo-semantic-skills` plugin - review, debug,
  regression-test, and record a *rendered* Odoo UI in a live browser (complementing the
  existing source-level skills). Four new skills:
  - `odoo-ui-reviewer` - five-lens verdict (aesthetics, functional correctness, runtime
    stability, accessibility, performance) on a rendered screen (slim; paired with the new
    `odoo-ui-reviewer` agent bundle).
  - `odoo-ui-debug` - root-cause a broken/misbehaving UI at runtime (console errors, failed
    requests, blank OWL renders, CSS that renders wrong) and point at the exact override point.
  - `odoo-visual-regression` - screenshot-baseline + diff between two Odoo states (before/after
    an upgrade, module install, theme change, or code edit) with blast-radius assessment.
  - `odoo-demo-recorder` - record an MP4/GIF screen-capture of a scripted Odoo click-path for a
    demo, sales walkthrough, or marketing clip.
- **`odoo-ui-reviewer` agent bundle** (`agents/odoo-ui-reviewer.md`, Sonnet) - drives the
  multi-step browser review with screenshot/console/Lighthouse evidence plus OSM source pointers.
- **Bundled browser MCP servers** (`.mcp.json`) - `chrome-devtools`, `playwright`, and
  `pagecast` (local stdio `npx` servers) load automatically when the plugin is installed,
  powering the visual stack.
- **`/odoo-semantic-skills:setup` command** - one-shot, idempotent, extensible setup for the
  visual workflow. Drives a registry of numbered step scripts (`scripts/setup-steps/`), each
  with a `describe | check | apply` contract: wires the 3 browser MCP servers across Claude
  Code / Codex CLI / Gemini CLI, installs browser dependencies (Node >= 20, Playwright
  Chromium, ffmpeg), auto-allows the browser tool permissions, discovers local Odoo repos into
  `.odoo-ai/instances.toml`, and optionally spins up a declared instance.
- **SessionStart hook** (`hooks/hooks.json` + `hooks/check-setup-deps.sh`) - read-only
  readiness probe that hints `/odoo-semantic-skills:setup` when visual-stack deps are missing;
  silent when everything is ready, never installs or blocks.
- **Shared setup utilities** (`scripts/lib/`) - `config_merge.py` (idempotent cross-runtime MCP
  config merge) and `discover_odoo.sh` (local Odoo instance discovery), reused by the
  setup-step scripts.

### Changed
- Plugin description + keywords bumped to reflect the visual stack - now **26 skill personas +
  3 specialist agents + 6 workflow commands** across engineering, sales, marketing, strategy,
  onboarding, and visual UI testing.
- Documentation counts corrected from `22 skills / 2 agents / 5 commands` to
  `26 skills / 3 agents / 6 commands` across `README.md` and `docs/setup.md`.
- **VERSION bumped** from `2.0.1` to `2.1.0`, kept in sync with the skills plugin's
  `plugin.json.version`.

## [2.0.1] - 2026-05-29

### Fixed
- **Broken docs anchor in `README.md`** - the MCP-resources link pointed at the stale
  `docs/setup.md#mcp-resources-7-uri-templates` fragment; corrected to the actual
  `plugins/odoo-semantic-skills/docs/setup.md#mcp-resources-odoo-uri-scheme-v05` heading.
- **Stylesheet resource URI template** corrected to
  `odoo://{version}/stylesheet/{module}/{file_path*}` (was missing the `{module}` segment
  and `*` wildcard), matching the server surface.
- **Module resource description** now notes the `license notice if restricted` line,
  aligning the README with the server surface.

### Changed
- **Server-surface reference bumped to v0.11.1** (from the v0.8 surface the changelog
  previously implied as current). The v0.11.1 surface keeps the 24-tool / 7-resource
  count and folds in the v0.9.1 `license_notice` output marker and the v0.10.0
  `module_inspect(method='dependencies')` capability, so the changelog no longer reads
  v0.8 as the live target.
- **README tested-build note** updated to Claude Code v2.1.156.

## [2.0.0] - 2026-05-29

### Changed
- **BREAKING:** Split the single `odoo-semantic` plugin into two: `odoo-semantic-skills`
  (22 skills + 2 agents + 5 workflow commands) and `odoo-semantic-mcp` (MCP server
  connection + `/odoo-semantic-mcp:connect`). Install either independently, or install
  `odoo-semantic-skills` to auto-pull `odoo-semantic-mcp` via the plugin dependency.
- Renamed the setup command `/odoo-semantic:connect` -> `/odoo-semantic-mcp:connect`.
- Relocated plugin content under `plugins/` (`plugins/odoo-semantic-skills/` and
  `plugins/odoo-semantic-mcp/`); updated `README.md` and `CONTRIBUTING.md` paths and
  per-client snippet/doc links accordingly.

### Migration
- Existing users: uninstall `odoo-semantic@viindoo-plugins`, then install
  `odoo-semantic-skills@viindoo-plugins` (pulls the MCP plugin), and re-run
  `/odoo-semantic-mcp:connect`. The MCP server name (`odoo-semantic`, tools
  `mcp__odoo-semantic__*`) is unchanged, and the marketplace name remains `viindoo-plugins`.

## [1.1.0] - 2026-05-28

### Changed
- **Full English rewrite of all top-level documentation** (`README.md`, `CHANGELOG.md`,
  `CONTRIBUTING.md`, `ROADMAP.md`, `BLOCKED_VERSIONS.md`, `CODE_OF_CONDUCT.md`,
  `NOTICE`, `VERSION`). No Vietnamese-language content remains in any public doc.
- **Neutralized Viindoo-specific framing** in `README.md`: "Viindoo CEO use case" ->
  "small-team founder use case"; "vs Viindoo" -> "vs your Odoo distribution"; Viindoo
  as legitimate project sponsor and trademark holder is retained throughout.
- **Replaced private server repository links** - all references to
  `github.com/Viindoo/odoo-semantic-server` replaced with the public hosted endpoint
  `https://odoo-semantic.viindoo.com/` or the sign-up page; self-host instructions
  redirect to post-registration server docs.
- **Fixed count claims** in `README.md`: "3 agents (2 + 1 deprecated)" corrected to
  "2 specialist agents" (deprecated agent removed from tree); "6 workflow commands"
  corrected to "5 workflow commands + 1 setup command (`/odoo-semantic:connect`)".
- **Added MCP resource URI templates section** to `README.md` documenting all 7
  `odoo://` resource templates and the 12 supported Odoo versions (v8.0 - v19.0).
- **VERSION bumped** from `1.0.0` to `1.1.0`.

No functional changes to skills, agents, or commands in this release.

## [1.0.0] - 2026-05-28

### Added
- 8 specialist personas: Engineer, Coder (agent+skill bundle), Code-Reviewer (agent+skill bundle), Pre-Sales Consultant, Sales AE, Marketer, Strategist, Onboarding/Concierge.
- 7 new skills: `odoo-frontend-coder` (merges legacy `odoo-js-coder` + `odoo-owl-coder` with v8-v19 internal version gate), `odoo-deal-followup`, `odoo-discovery-summarize`, `odoo-content-draft`, `odoo-campaign-plan`, `odoo-competitive-brief`, `odoo-deploy-checklist`.
- 2 new agent bundles in `agents/`: `odoo-coder` + `odoo-code-reviewer` (restricted-tool autonomy for code-write work).
- 5 slash command-recipes in `commands/`: `/odoo-bid-respond`, `/odoo-customer-followup-draft`, `/odoo-discovery-quick`, `/odoo-feature-positioning`, `/odoo-upgrade-plan-full` (replaces legacy `odoo-upgrade-planner` agent).
- `odoo-router` skill - silent disambiguation concierge with 21-row routing table + 4 collision-test cases.
- `odoo-onboard` skill - bootstrap Odoo project context to `.odoo-ai/context.md` (gitignored, portable markdown-bullet schema).
- SSOT generator (`generator/gen_surface.py`) - emits routing matrix + per-skill `## MCP tools` blocks + IDE snippets from `generator/server-surface.json`. Idempotent.
- Skill↔tool dependency map (`generator/skill_tool_deps.json`) + CI assertion (`generator/check_deps.py`) - fails if a skill/agent references a removed server tool.
- Confidentiality pre-commit hook + CI workflow - blocks vault paths and absolute `~/.` references in committed files.
- Multi-runtime smoke test checklist (`tests/smoke/runtime_parity.md`).
- README section "For the small-team Odoo founder" with use cases covering all 8 personas.
- `## Out of Scope` + `## Standalone-first fallback` sections in all 22 skills + 5 of 5 new commands (CI-enforced by `tests/test_skill_format.py`).
- Agent format tests (`test_agent_frontmatter`, `test_agent_depth_rule_guard`, `test_agent_skill_invocation_guard`) covering the 2 active specialist agents.

### Changed
- Plugin description + keywords updated to reflect post-refinement scope.
- 11 existing skills (`odoo-addon-diff`, `odoo-capability-proof`, `odoo-customization-inventory`, `odoo-deprecation-audit`, `odoo-feature-check`, `odoo-feature-highlights`, `odoo-gap-analysis`, `odoo-objection-handler`, `odoo-override-finder`, `odoo-risk-overview`, `odoo-version-diff`) gained `## Out of Scope` + `## Standalone-first fallback` sections.
- `odoo-coder` + `odoo-code-reviewer` skills slimmed (≤100 lines each) into agent+skill bundle pattern; execution detail moved to `agents/<name>.md`.
- `docs/reference/mcp-tool-routing.md` (442 lines) - fully generator-managed, no longer hand-maintained.

### Removed
- `skills/odoo-js-coder/` + `skills/odoo-owl-coder/` (merged into `odoo-frontend-coder`).
- Hardcoded `SKILL_TO_TOOLS` Python dict in generator - replaced by JSON SSOT in `skill_tool_deps.json`.

### Deprecated
- `agents/odoo-upgrade-planner.md` - kept in tree for git history but marked DEPRECATED; users should invoke `/odoo-upgrade-plan-full` slash command instead.

### Fixed
- Generator `description.split(".")[0]` clipping bug (truncated descriptions at inline periods like `@api.depends`, decimal version numbers).
- Confidentiality leak: 3 files referenced an absolute `~/.claude/plans/...` path - replaced with in-repo `docs/refinement-plan-2026-05-28.md`.
- 4 skills had redundant handwritten `## Additional tools (ollama-delegate)` section duplicating generator-managed content - removed.
- Agent bundle tools allowlist missing `set_active_version` - both `odoo-coder` and `odoo-code-reviewer` agents had this fixed (would have caused runtime denial of the first MCP call).
- Marker labels in 5 new B.2 skills renamed from `BEGIN GENERATED TOOLS` to honest `BEGIN MANUAL TOOLS - <name>` (since these skills are in `SKIP_SKILL_DIRS`).

### Refinement history (v0.8 → v1.0)

Plugin grew from a thin 24-tool OSM mirror into a 22-skill + 2-agent + 5-workflow-command
AI workforce toolkit organized around 8 specialist personas (Engineer, Coder,
Code-Reviewer, Pre-Sales, Sales AE, Marketer, Strategist, Onboarding-Concierge).

Delivered across 4 phases (Foundation → Specialists → Workflows → Polish) in
a multi-wave parallel orchestration using Sonnet subagents with disjoint file
ownership. Key engineering decisions: persona-as-skill-default with two
agent+skill bundles for restricted-tool autonomy; SSOT generator for tool surface;
skill-creator quality-gated router and onboard skills; depth-rule enforced at
every subagent prompt.

Detailed orchestration log retained internally.

### Migration notes
- Users invoking the legacy `odoo-upgrade-planner` agent should switch to `/odoo-upgrade-plan-full` slash command.
- `commands/discovery-summarize.md` was renamed to `commands/discovery-quick.md` (slash command is now `/odoo-discovery-quick` - the skill `odoo-discovery-summarize` retains its name for natural-language invocation).
- Custom modules using `odoo-js-coder` / `odoo-owl-coder` skill names should switch to `odoo-frontend-coder` (handles both legacy and OWL based on detected version).

### Deferred to v1.1.0
- AC-D6: router trigger optimization via `/skill-creator` Mode 5 + `run_loop.py`. The 20-query eval set is authored in `skills/odoo-router/evals/evals.json` (15 cases) + the 5 collision-test cases in `skills/odoo-router/SKILL.md`. Mode 5 requires the Claude Code subprocess API, which is CC-only; multi-runtime parity is verified manually via `tests/smoke/runtime_parity.md` for v1.0.0. Re-runnable in v1.1.0 after multi-runtime smoke is fully executed.
- AC-D8 CI version-sync test: VERSION ↔ plugin.json sync is currently manual. Add a CI assertion in v1.1.0 (e.g., `test_version_sync` in `tests/test_plugin_schema.py`).
- Confidentiality scan marker convention: PR #14 wave-2 removed the file-name allowlist entirely by moving the refinement plan to an internal planning document. v1.1.0 may adopt an opt-in HTML marker convention (e.g., `<!-- confidentiality-exempt: reason -->`) if any future public doc must legitimately reference an internal-only path - currently no such file exists, so defense-in-depth is restored without an allowlist.

## [0.8.0] - 2026-05-21

### Changed (server v0.9.1 surface alignment)
- **`license_notice` output marker** - `describe_module` and `module_inspect(method='summary')` (and the `odoo://{version}/module/{name}` resource) may now emit a `License notice:` line for license-restricted modules. OEEL-1 modules are skipped by default, so the notice is the intentional, non-silent marker that content is withheld - documented as such in the routing matrix so an AI client treats it as expected, not a missing-data bug to retry around.
- **`lint_check(language='xml')` clarified as corpus-level** - the server lints indexed views against the version-exact grammar at index time, exposing server-indexed XML lint findings. The `xml` mode returns those findings for a version and **ignores the `code` argument** (it is not a snippet check). Documented in the `lint_check` routing-matrix entry. No new tools - server tool surface remains 24.

### Changed (server v0.9.0 surface alignment)
- **`view_type` gains `'list'` value** (v18+ alias for `'tree'`) - documented in `view_type`
  arg descriptions for `model_inspect` and `module_inspect` across the routing matrix and all
  adapter snippets (Cursor, Gemini Gem, OpenAI Custom GPT).
- **`.less` stylesheet coverage** - `resolve_stylesheet` and `find_style_override` now cover
  CSS, SCSS, and LESS files (LESS targets legacy v8-v11 modules). Updated routing matrix §2
  tool entries, legend, dev persona, and all adapter snippets to read "CSS/SCSS/LESS".

### Added (v0.8 server surface)
- **4 new ORM-validation tools** documented across all adapter snippets (Cursor, Gemini
  Gem, OpenAI Custom GPT), routing matrix §1 & §2, Appendix table, dev persona, and the
  `odoo-coder` / `odoo-code-reviewer` skills. Static checks against the indexed graph that
  let an AI client catch hallucinated field-paths, operators, dependencies, and relation
  targets *before* it emits a domain / `@api.depends` / relational field:
  - **`resolve_orm_chain(model, dotted_path, odoo_version)`** - walks a dotted field path
    (e.g. `partner_id.country_id.code`) hop by hop, returning the terminal field type or a
    `BROKEN` line naming the first unresolved hop.
  - **`validate_domain(model, domain, odoo_version)`** - validates each `(field_path,
    operator, value)` term of a search domain. Operator validity is **version-aware**:
    `parent_of` from v9, `any`/`not any` only from v17, v19 access-rights variants.
  - **`validate_depends(model, method, odoo_version)`** - validates a compute method's
    indexed `@api.depends('a.b', ...)` paths; flags depends on `id` and suggests the closest
    field name for typos. Era1 (v8/v9) surfaces a clear "no @api.depends" note.
  - **`validate_relation(model, field, target_model, odoo_version)`** - asserts a field is a
    many2one/one2many/many2many whose comodel is `target_model` (or a subtype via
    inheritance); reports the actual comodel on mismatch.

### Changed
- **Target server v0.8 tool surface (20 → 24 tools).** Mirrors server v0.8.0. `tools/list` now reports 24 tools. Version references across README,
  routing matrix, dev persona, snippets, and setup docs bumped v0.7 → v0.8.

### Dependencies
- The 4 ORM-validation tools require server **v0.8.0**. `validate_depends`
  additionally requires a server-side backfill operation (see server docs) - until it runs,
  `validate_depends` returns the "no @api.depends" note for methods indexed before the
  reindex. The backfill introduces no new MCP tools (surface stays 24), so this client
  release needs no tool changes for it; recommend landing this release alongside that
  reindex so `validate_depends` is fully functional on the live surface.

## [0.7.0] - 2026-05-21

### Added (v0.7 server surface)
- **2 new stylesheet tools** (`resolve_stylesheet`, `find_style_override`) added to all
  adapter snippets (Cursor, Gemini Gem, OpenAI Custom GPT), routing matrix §1 & §2,
  Appendix table, and dev persona. `resolve_stylesheet` enumerates a module's CSS/SCSS
  files; `find_style_override` does pgvector semantic search (with import-chain traversal) for
  selector/variable origin and overrides.
- **`from_module` filter** on `model_inspect` (method=`summary`/`fields`/`field`) and
  `entity_lookup` (kind=`model`/`field`) - restrict results to declarations from a
  specific module.
- **`kind` filter** on `model_inspect` (method=`fields`) - filter fields by type
  (e.g. `'many2one'`).
- **`view_type` filter** on `model_inspect` (method=`views`) and `module_inspect`
  (method=`views`) - filter by view type (e.g. `'form'`/`'tree'`).
- **`bound_model` filter** on `module_inspect` (method=`owl`) - restrict OWL components
  to those bound to a specific model.
- **`era` filter** on `module_inspect` (method=`js`) - filter JS patches by era
  (`era1`/`era2`/`era3`).
- **`noqa` support in `lint_check`** - inline `# noqa: RULE_ID` (or bare `# noqa`) in
  the `code` argument suppresses findings on that line. Documented in routing matrix,
  all three adapter snippets, and both affected skills (`odoo-coder`,
  `odoo-code-reviewer`).

### Changed (v0.6 migration - also part of this release)
- **Target server v0.6 tool surface.** The upstream server removed the 10
  deprecated flat tools (`resolve_model`, `resolve_field`, `resolve_method`,
  `resolve_view`, `list_fields`, `list_methods`, `list_views`, `list_owl_components`,
  `list_qweb_templates`, `list_js_patches`) per server ADR-0028. All client adapter
  snippets (Cursor, Gemini Gem, OpenAI Custom GPT), persona docs, and the routing
  matrix have been migrated to reference the 3 superset discriminator tools
  (`model_inspect`, `module_inspect`, `entity_lookup`) that replace them.
- **Removed `odoo-router` classifier agent.** The agent was redundant: Claude Code
  discovers available tools at runtime via the MCP `tools/list` call, and the 3
  superset discriminator tools (`model_inspect`, `module_inspect`, `entity_lookup`)
  handle entity-type routing server-side without a dedicated client-side classifier.
- **Replaced hardcoded tool counts with capability phrasing** across README, snippets,
  and persona docs so the count never drifts out of sync with the server again.
- **Fixed `module_inspect` arg name drift**: routing matrix and adapter snippets now
  consistently use `name` (required) instead of `module` for the module name parameter.

## [0.5.0] - 2026-05-21

### Added
- `BLOCKED_VERSIONS.md` kill-switch registry: add a short SHA to block automatic
  marketplace pin for known-bad commits; `pin-sha.yml` reads the table and skips
  the pin step (fail-soft - CI stays green) when the HEAD SHA matches.
- `commands/connect.md`: added missing `name: connect` frontmatter field to match
  agent/skill convention (`name:` before `description:`).
- Initial **public** release of the Odoo MCP Client as a standalone MIT-licensed
  repository, split out of the `odoo-semantic` monolith.
- 15 persona-specific skills (CEO, Developer, Consultant, Marketer, Sales).
- 2 orchestration agents (`odoo-router`, `odoo-upgrade-planner`).
- `/odoo-semantic:connect` command for one-step MCP server setup.
- Multi-client MCP config snippets (Cursor, ChatGPT Custom GPT, Gemini Gem).
- Per-persona quick-start guides under `docs/personas/`.

### Notes
- This client targeted the v0.5.0 server tool surface (28 tools + 7 MCP Resources).
  The 10 legacy `resolve_*` / `list_*` tools were deprecated and have since been
  removed in the server's v0.6 (see [0.6.0] above).

## [0.4.x] - 2026-04-15

- Pre-split history. The plugin shipped as `dist/odoo-semantic-plugin/` inside the
  monolith repository. Full server-side changes for this period are recorded in the
  server CHANGELOG (available after sign-up at https://odoo-semantic.viindoo.com/).

## [0.3.x] - 2026-03-01

- M7.5 persona-skill batch: the original 15-skill set and routing agents were
  introduced. See the
  server CHANGELOG (available after sign-up at https://odoo-semantic.viindoo.com/)
  for the detailed history.
