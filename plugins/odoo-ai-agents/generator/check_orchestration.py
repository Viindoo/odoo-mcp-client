#!/usr/bin/env python3
"""
check_orchestration.py - lint the Declarative Capability & Contract Layer.

Validates that orchestration metadata (generator/skill_tool_deps.json -> "orchestration")
is complete and that skills thread the shared contracts they are required to:

  1. Coverage     - every skills/<dir> has an orchestration entry, and vice versa.
  2. OSM-first    - skills that spawn/fan-out workers writing Odoo (workflow-chaining,
                    odoo-brl) reference snippets/osm-first-contract.md.
  3. Design-sys   - skills with stack in {frontend, fullstack} reference
                    skills/_shared/odoo-frontend-fidelity.md.
  4. Instance     - skills with instance_touching=true reference cli_help / the lifecycle
                    docs (so they ground the CLI per target version instead of assuming).
  5. Spawn truth  - spawn_class is consistent with the SKILL.md body: neither a 'leaf' nor
                    an 'orchestrator-nl' (chains skills via NL dispatch, no subagent spawn)
                    may show active named-agent dispatch/launch language; a 'spawner-agent'
                    is unconstrained here (the orchestration SSOT is authoritative for it).
  6. CHP          - a skill declaring handoff in {send-message, fork} documents the Tier-C
                    (fresh spawn) fallback in its body.
  7. No hardcode / no leak - self-referential CSS custom properties, machine-specific
                    absolute paths, and hardcoded hex inside skill SCSS code fences.
  8. Agent role   - LIVE and enforcing (all agents now carry a `role` in the SSOT). Two checks:
                    (i) coverage - every agents/<name>.md on disk must have a `role` entry in
                    skill_tool_deps.json "agents"."<name>"."role" (a wholly-unregistered agent
                    is a finding, mirroring rule 1's skill-side coverage); (ii) for a `role: leaf`
                    agent, its body must carry the never-SPAWN clause and show neither positive
                    spawn language nor a positive git-mutation instruction. (Historically this
                    pass shipped INERT while `role` was unpopulated; it now bites - roles landed.)
  9. wait-scope   - WARN-ONLY (see below). Ground truth (see R0, spawner-completion-contract.md):
                    a subagent CAN launch a child and block on it (a blocking Agent-tool launch),
                    and MUST when it needs the result - only the root conversation is resumed when
                    a background child finishes, so a subagent that parks instead never wakes at
                    all. Async park is therefore a root-only branch. A park/wait instruction
                    (end turn / park / hold until / wait to be resumed / await) near turn/child/
                    worker/agent vocabulary, anywhere under skills/*/SKILL.md, agents/*.md,
                    snippets/*.md, is a finding when EITHER of two real hazards is present: (a) its
                    section names no R0 branch (no R0/move-N/run_in_background/NEEDS_NEXT/
                    nesting-cap/spawner-completion-contract.md citation) - an unattributed park
                    instruction leaves a reader unable to tell which of the three R0 moves it is
                    exercising; (b) its section shows file-writing language (write/author/edit) but
                    states no commit/checkpoint safeguard - the non-interactive-surface hazard R0
                    itself names: never end a turn with uncommitted work.
 10. wait-mechanism - WARN-ONLY (see below). Two real hazards, neither ever correct under any R0
                    branch: (a) an instruction to POLL or SLEEP while waiting for a child - a
                    blocking launch (`run_in_background: false`) already blocks the call itself,
                    and an async launch parks via end-of-turn, so nothing ever legitimately polls
                    or sleeps FOR a child's completion (a periodic task-list status check is a
                    DIFFERENT, sanctioned pattern - tracking status, not busy-waiting - and is
                    excluded); (b) a claim that a dispatch happened (launch/dispatch/invoke
                    the Agent tool) with no nearby capability-handling language (own toolset /
                    Agent tool absent / nesting cap / R0 / NEEDS_NEXT) - R0 move 1 requires
                    checking your own toolset FIRST, so a dispatch claim with no cap-check nearby
                    reads as though the Agent tool is always assumed present.
 11. role-scope   - LIVE and enforcing. Data-driven from `agents.<name>.role` (never a hardcoded
                    name list). Two halves: (a) a `role: leaf` agent body may not cite any member
                    of the spawner-tier set (`spawner-completion-contract.md`,
                    `concurrency-guard.md`) - a leaf launches nothing, so those
                    contracts do not bind it (see `snippets/spawner-completion-contract.md`'s own
                    "vacuously compliant" sentence); (b) a `role: spawner|coordinator` agent body
                    MUST cite `spawner-completion-contract.md`. Half (b)'s subject set (agents with
                    role in {spawner, coordinator}) is asserted NON-EMPTY before the check runs -
                    an empty subject set would let half (b) pass vacuously (zero agents checked,
                    zero findings), so an empty set is itself a finding unless the registry sets
                    the explicit top-level flag `_role_scope_no_spawners_expected: true`.
 12. brief-fields - WARN-ONLY, PERMANENTLY (not a migration window - see docstring below). For
                    every dispatch edge, report any key in `agents.<agent>.brief.required` that
                    never appears inside the DISPATCHER's own dispatch fences (fenced ``` code
                    blocks) - the literal brief template that dispatcher hands the agent. Two edge
                    tiers, because a brief is written by whoever actually fills it: skill->agent
                    from `orchestration.<skill>.spawns_agents`, MINUS any agent that a coordinator
                    in that same list dispatches (that field is a REACHABILITY set feeding the
                    generated ORCHESTRATION-MAP, so a leaf under a coordinator appears there
                    without the skill ever writing its brief - charging the skill for it yields a
                    finding no edit to the skill can clear); and agent->agent from
                    `agents.<dispatcher>.spawns_agents`, the tier where a coordinator's own leaf
                    briefs live. Measured reality this rule exists to surface, not hide: 39 real
                    dispatch briefs across 133 ad-hoc key names, none carrying all four ALWAYS-tier
                    fields - see M7 in `12-design-final.md`. Full corpus normalization is
                    explicitly out of scope; this rule reports the diff and blocks nothing.
 13. card-budget    - LIVE and enforcing (M9, 12-design-final.md). Data-driven, and a file
                    qualifies through EITHER of two doors. Door (a) DECLARED: it carries an entry
                    in `tests/fixtures/card_budget_grandfather.json` (checked-in data, generated
                    ONCE at the start of the M9 wave from files that already exceeded the cap and
                    sit OUTSIDE that wave's 13 inverted files); the entry is both the qualification
                    and the budget, and it is measured wherever the file lives. Door (b)
                    DISCOVERED: it is a `snippets/*.md` or `skills/_shared/*.md` file cited by >=3
                    distinct skills+agents (a "hot" shared contract), and its budget is the default
                    cap (4,096 B). Door (b) is a heuristic for hotness that door (a) states
                    outright - which is how a hot contract door (b) cannot see gets capped: a
                    top-level `skills/<name>/SKILL.md` runtime contract (e.g. `run-harness`, the
                    drive-to-done loop re-entered on every node and every resume) shares the
                    basename `SKILL.md` with every skill, so no basename-keyed citer count can
                    single it out. A wave-13 file earns its own permanent budget entry the moment
                    it is trimmed and committed - that entry is its post-trim actual size, so the
                    rule fires only on (a) a listed file that GROWS past its recorded budget, or
                    (b) a NEW file (no grandfather entry) entering the >=3-citer set above the
                    default cap.
 14. ref-scope      - (M9, 12-design-final.md). Two independent halves, DIFFERENT gate status:
                    (a) WARN-ONLY FOR ONE RELEASE - a `skills/*/SKILL.md` or `agents/*.md` body
                    may not cite another file (a real relative path, not a bare filename - avoids
                    colliding every skill's own `SKILL.md`) larger than 20,480 B without a
                    `§ <anchor>` within 150 chars of the citation; a real measured backlog (81
                    findings, dominated by two non-wave-7 files) means this ships loud-but-inert
                    like rules 9-10, not silently declared - see
                    check_ref_scope_citation_anchor's docstring. (b) LIVE and enforcing - NO file
                    under `skills/`, `agents/`, or `snippets/` may contain the substring
                    `snippets/references/` - the read-both hazard closure: an executing agent must
                    never be handed a pointer to the reference sibling it could follow instead of
                    the (now-inverted) decidable rule file. `docs/` is exempt from (b) - the
                    reference tree is discoverable from `docs/authoring-skills-and-agents.md` and
                    from this lint, by design.
 15. no-provenance  - LIVE and enforcing (M10, X-50, 12-design-final.md). Agent-facing prose
                    carries no PLUGIN-SELF changelog / issue-tracking provenance: the internal
                    `(V-NN...)` / `(Problem N)` tags, the changelog vocabulary a rewrite leaves
                    behind (`Replaces `, `formerly`, `renamed from`, `was previously`,
                    `as of version`, `since 4.x`, `new in 4.x`, `deprecated in favour of`,
                    `legacy `, `no longer exists`, `moved here from`, `originally lived in`,
                    `consolidated from`), and issue/PR references (`see PR`, `tracked in`,
                    a qualified `PR #123` / `issue #7`). Scanned over the WHOLE agent-facing
                    corpus (`agent_facing_files()` - skills/, agents/, snippets/, commands/,
                    workflows/, plus the docs/ files agent-facing prose actually points an agent
                    at), not just the first three trees. The discriminator: RESIDUE narrates what
                    THIS PLUGIN used to do (free to delete - git has it); OPERATIVE text tells the
                    agent what to DO about something that still exists (deleting it breaks a live
                    consumer). Guards, all window-scoped: (1/1b/1c/1d) the match names a domain
                    OUTSIDE this plugin - an Odoo version anchor or role-named series
                    (`<src-series>`), an Odoo framework-era idiom (`web.Widget`, `oe_*`), the
                    PROSPECT's incumbent system ("legacy POS", "legacy accounting software"), or
                    the codebase under work evolving (Odoo core absorbed it, the rebase base
                    superseded it); (1e) the file itself DEFINES a legacy era in a heading with an
                    Odoo version anchor (`## Legacy v8-v14 workflow`), so a later bare `legacy` is
                    anaphoric to that defined term; (2) the match sits inside a double-quoted span
                    (a quoted user utterance / routing trigger, e.g. `"review PR #123"`, is not the
                    file asserting its own history); (3) OPERATIVE BACK-COMPAT - the window carries
                    handling vocabulary ("back-compat", "read only as a fallback", "is still read",
                    "treats ... as"), which only ever accompanies a live instruction about a shape
                    still in the wild. Guard 3 is offered ONLY to alternatives that can name such a
                    shape (`legacy`, `no longer exists`, `formerly`, ...), never to a pure
                    provenance tag like `(V-34)` or `see PR #12`.
 16. instance-truth - the `instance_touching` field checked against the SKILL.md body instead of
                    against its own derivation. Two halves, DIFFERENT gate status.
                    (a) LIVE and enforcing - `instance_touching: true` with NO instance evidence
                    anywhere in the skill's own body is a finding. Every other lint rule reads this
                    field as an input; `_derive_gate_tier` turns it straight into `L2`, an ALWAYS-
                    human gate the autonomy dial can never lower. So a `true` nothing in the skill
                    supports does not merely mislabel - it stops an otherwise-automatic run and
                    asks a human to authorize an irreversible act the skill never performs.
                    Evidence is read from the body with the GENERATED `## MCP tools` region cut
                    out: that region is emitted from the tool surface and mentions `odoo-bin` in a
                    `cli_help` blurb for skills that never touch an instance, which is exactly how
                    a bare grep would certify a false declaration.
                    (b) WARN-ONLY, and it says why below - `instance_touching: false` while the
                    body shows STRONG evidence (an allocator lease call, or an active dispatch of
                    the instance front door) is printed with that evidence but never gates. It
                    cannot gate yet because `_derive_gate_tier` still maps ANY `true` to `L2`,
                    while the runtime sheets deliberately hold two such skills at `L1` on the
                    ground that their instances are EPHEMERAL and self-released - so correcting
                    those rows today would ADD human gates the tree elsewhere says must not exist.
                    Half (b) makes that contradiction visible on every run; it flips to strict in
                    the change that stops tier policy keying `L2` off the bare fact.

WARN-FIRST: by default this prints findings and exits 0 (migration-friendly). Pass --strict
(or set ORCH_STRICT=1) to exit 1 on any finding from rules 1-8, 11, 13, 14b, 15, and 16a - flip that on
once all skills comply. Rules 9-10 ([wait-scope]/[wait-mechanism]) and 14a (ref-scope's citation-
anchor half) are additionally WARN-ONLY FOR ONE RELEASE BY DESIGN, independent of --strict/
ORCH_STRICT: they are new and proximity/citation-based (not a full semantic read, and - for 14a -
measured against a real backlog this wave did not have time to individually verify site-by-site),
so a false positive or a hastily-placed meaningless anchor is a real risk - they print but never
flip the exit code. Flip them into the strict gate (fold their list into `findings`) once the tree
is clean, one release after they ship. Rule 12 ([brief-fields]) is warn-only PERMANENTLY, by
design (see rule 12 above) - it is never scheduled to flip, unlike rules 9-10 and 14a.

Run from the repo root or anywhere; paths are resolved relative to this file.
"""

import json
import os
import re
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent.resolve()
REPO_ROOT = PLUGIN_ROOT.parent.parent
DEPS_FILE = Path(__file__).parent / "skill_tool_deps.json"
SKILLS_DIR = PLUGIN_ROOT / "skills"
AGENTS_DIR = PLUGIN_ROOT / "agents"
SNIPPETS_DIR = PLUGIN_ROOT / "snippets"
COMMANDS_DIR = PLUGIN_ROOT / "commands"
WORKFLOWS_DIR = PLUGIN_ROOT / "workflows"
DOCS_DIR = PLUGIN_ROOT / "docs"
REFERENCES_DIR = SNIPPETS_DIR / "references"
SHARED_DIR = SKILLS_DIR / "_shared"

# --- The agent-facing corpus (what a content rule is allowed to see) --------------------------
#
# `skills/`, `agents/`, `snippets/`, `commands/`, and `workflows/` are agent-facing IN FULL: every
# file in them is prose (or declarative YAML) a running agent reads. `docs/` is MIXED - some of it
# is an authoring guide addressed to a HUMAN contributor, some of it is reference material that
# agent-facing prose sends an agent off to read mid-run. Rather than hardcode which is which, the
# in-scope docs set is DERIVED: a docs file is agent-facing exactly when the per-invocation corpus
# cites it (see `agent_facing_docs`).

# A `docs/<...>.md` citation. Requires a real relative path so a bare `setup.md` cannot collide.
DOC_CITE_RE = re.compile(r"\bdocs/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_.-]+)*\.md\b")

# Explicit carve-out: the authoring guide is addressed to a HUMAN authoring a skill/agent, not to an
# agent executing one, so it stays out of scope even if agent-facing prose starts citing it.
AGENT_FACING_DOCS_EXCLUDED = ("docs/authoring-skills-and-agents.md",)


def _doc_citing_files() -> list[Path]:
    """The PER-INVOCATION corpus whose citations define which docs/ files are agent-facing.

    `snippets/references/` is excluded as a citer on purpose: per M9 / [ref-scope] half (b) it is
    the read-if-you-need-the-why tier that no executing agent is ever pointed at, so what IT cites
    says nothing about what an agent is handed mid-run."""
    files = list(SKILLS_DIR.rglob("*.md")) if SKILLS_DIR.exists() else []
    if SNIPPETS_DIR.exists():
        files += [f for f in SNIPPETS_DIR.rglob("*.md") if f.parent != REFERENCES_DIR]
    if AGENTS_DIR.exists():
        files += list(AGENTS_DIR.glob("*.md"))
    if COMMANDS_DIR.exists():
        files += list(COMMANDS_DIR.glob("*.md"))
    if WORKFLOWS_DIR.exists():
        files += list(WORKFLOWS_DIR.glob("*.md")) + list(WORKFLOWS_DIR.glob("*.yaml"))
    return files


def agent_facing_docs() -> list[Path]:
    """Every `docs/` file the per-invocation corpus actually points an agent at, on disk.

    Data-driven, never a hardcoded list: a new reference doc enters scope the moment a skill/agent/
    snippet/command/workflow cites it, and leaves scope when the last citation goes."""
    if not DOCS_DIR.is_dir():
        return []
    cited: set[str] = set()
    for f in _doc_citing_files():
        cited.update(m.group(0) for m in DOC_CITE_RE.finditer(f.read_text(encoding="utf-8")))
    cited -= set(AGENT_FACING_DOCS_EXCLUDED)
    return sorted(p for p in (PLUGIN_ROOT / rel for rel in cited) if p.is_file())


def agent_facing_files(include_docs: bool = True) -> list[Path]:
    """Every file a running agent may be handed - the scan corpus for the content rules.

    `include_docs=False` is for [ref-scope] half (b), whose own contract exempts `docs/` (the
    reference tree is meant to stay discoverable from the authoring guide and from this lint)."""
    files = list(SKILLS_DIR.rglob("*.md")) if SKILLS_DIR.exists() else []
    if SNIPPETS_DIR.exists():
        files += list(SNIPPETS_DIR.rglob("*.md"))
    if AGENTS_DIR.exists():
        files += list(AGENTS_DIR.glob("*.md"))
    if COMMANDS_DIR.exists():
        files += list(COMMANDS_DIR.glob("*.md"))
    if WORKFLOWS_DIR.exists():
        files += list(WORKFLOWS_DIR.glob("*.md")) + list(WORKFLOWS_DIR.glob("*.yaml"))
    if include_docs:
        files += agent_facing_docs()
    return sorted(set(files))

# M9 (12-design-final.md): the 13 files inverted to their measured minimum. Each earns a sibling
# `snippets/references/<name>.md` carrying the explanation moved out of the per-invocation path.
# Data-driven single list - both the [ref-target] existence check and (informationally) the
# card-budget grandfather generator key off this same set.
INVERTED_SNIPPETS = (
    "snippets/dispatch-brief.md",
    "snippets/module-coordination-ledger.md",
    "snippets/git-delegation.md",
    "snippets/resource-teardown-contract.md",
    "skills/_shared/concurrency-guard.md",
    "snippets/worker-brief.md",
    "snippets/spawner-completion-contract.md",
    "snippets/continuation-contract.md",
    "snippets/worklog-contract.md",
    "snippets/test-first-contract.md",
    "snippets/state-root-resolution.md",
    "snippets/instance-handle-contract.md",
)

OSM_SNIPPET = "osm-first-contract"
DESIGN_DOC = "odoo-frontend-fidelity"
DESIGN_DOC_PATH = "skills/_shared/odoo-frontend-fidelity.md"
INSTANCE_REFS = ("cli_help", "INSTANCE-LIFECYCLE", "ODOO-TESTING")

# Per-version coding-guidelines SSOT: a root index plus a self-contained directory per series.
# Engineering agents read these before writing (read-before-write); a missing index breaks the
# version-aware lookup, so verify the root + each version index exists on disk.
CODING_GUIDELINES_ROOT = "skills/_shared/coding_guidelines"
CODING_GUIDELINES_VERSIONS = ("14.0", "15.0", "16.0", "17.0", "18.0", "19.0")

# Skills that fan-out / spawn workers which may write Odoo code → must carry OSM-first.
# (run-harness is deliberately NOT here: it is the domain-agnostic driver - "No OSM dependency" -
# and grounding is each dispatched specialist's concern, so it carries no osm-first contract.)
OSM_REQUIRED = {"workflow-chaining", "odoo-brl"}

# Allowed enum values for the orchestration SSOT. A typo (e.g. "spawner_agent") must be a
# loud finding, not a silent drop from the generated digest - otherwise the planner is told
# a real spawner is safe to forbid (typo enum lets the planner be deceived into thinking
# the skill is a safe non-spawner).
VALID_SPAWN_CLASS = {"leaf", "orchestrator-nl", "spawner-agent"}
VALID_STACK = {"backend", "frontend", "fullstack", "none"}
# agents.<name>.role enum (V-01 SSOT - now populated for every agent; see the agent-role pass below).
VALID_AGENT_ROLE = {"leaf", "spawner", "coordinator"}
# output_mode drives the Plan-Mode decision; default_gate_tier drives the run-harness gate
# policy. Both are SSOT here (replacing the hardcoded chat-only lists). output_mode is read
# per-skill from the SKILL.md Output field (a backend-stack skill can be read-only/chat-only,
# so it is NOT derived from stack). default_gate_tier IS derived once output_mode is known.
VALID_OUTPUT_MODE = {"chat-only", "writes-files"}
VALID_GATE_TIER = {"L0", "L1", "L2"}
# Context-Handoff Protocol (CHP) tier declared per skill. send-message = Tier-A (a launcher
# resumes a child it launched, by the id its own launch returned); fork = Tier-B
# (subagent_type=fork fan-out); fresh = Tier-C default (cold-spawn every turn - always correct
# baseline). Absence == fresh.
VALID_HANDOFF = {"send-message", "fork", "fresh"}


def _derive_gate_tier(spawn_class: str, instance_touching: bool, output_mode: str,
                      outward: bool = False) -> str:
    """Derive the registry default_gate_tier for a SKILL. L2 = irreversible/outward → ALWAYS
    human gate (the dial can never lower it). L1 = writes internal files. L0 = read-only/chat.

    This derives a SKILL's registry default only. The per-NODE tier is a total function in
    `run-harness` that also reads whether the node is dynamic and whether the driver itself
    composed a fresh-database brief; it is not computed here. `outward` is checked first so an
    outward skill always derives L2."""
    if outward:
        return "L2"
    if instance_touching:
        return "L2"
    if output_mode == "writes-files":
        return "L1"
    return "L0"

# High-precision ACTIVE dispatch signals in a SKILL.md/agents/*.md body. Deliberately narrow: a
# generic "spawn subagents" phrase is NOT included because it appears in negated capability
# statements ("this skill does not invoke other skills or spawn subagents") and is pure noise. We
# only flag the dangerous drift - a skill/agent declared `leaf` (or `orchestrator-nl`) that
# actively dispatches an agent. The orchestration/agent-role SSOT (skill_tool_deps.json) is the
# authoritative classification. Backtick-tolerant: prose commonly names the target agent in
# backticks ("launch the `odoo-test-writer` agent") - the bare-word-only form missed that.
SPAWN_BODY_RE = re.compile(
    r"(invoke the Agent tool|call the Agent tool"
    r"|dispatch(?:es)? (?:to )?the `?[a-z][a-z-]+`? agent"
    r"|launch(?:es|ing)? (?:the )?`?[a-z][a-z-]+`? agent)",
    re.I,
)
# Negation tokens that suppress a spawn match. Note: "non-" is deliberately excluded - it
# matches innocuous words like "non-blocking"/"non-trivial" and caused false negatives.
NEGATION_RE = re.compile(r"(\bnot\b|\bnever\b|\bcannot\b|n't\b|\bno longer\b)", re.I)


def _has_positive_spawn(body: str) -> bool:
    """True if the body shows a real (non-negated) active agent-dispatch instruction."""
    for m in SPAWN_BODY_RE.finditer(body):
        preceding = body[max(0, m.start() - 45):m.start()]
        if NEGATION_RE.search(preceding):
            continue  # e.g. "do NOT invoke the Agent tool" / "does not dispatch the X agent"
                      # / "cannot launch the X agent" - "cannot launch agents" (no named agent)
                      # never matches the regex at all, so it needs no negation guard here
        return True
    return False


# Agent-role pass (§7) detectors. GIT_MUTATION_RE mirrors the exact verb list from the V-01 spec
# (`git (commit|add|push|rebase|merge|reset|cherry-pick|stash|tag|checkout|branch)`); reuses the
# SAME NEGATION_RE lookback as _has_positive_spawn so "does NOT run git commit" is not a finding.
GIT_MUTATION_RE = re.compile(
    r"\bgit (commit|add|push|rebase|merge|reset|cherry-pick|stash|tag|checkout|branch)\b",
    re.I,
)


def _has_positive_git_mutation(body: str) -> bool:
    """True if the body shows a real (non-negated) git-mutation instruction - a `role: leaf`
    agent must never carry one (see snippets/git-delegation.md: leaves never run git)."""
    for m in GIT_MUTATION_RE.finditer(body):
        preceding = body[max(0, m.start() - 45):m.start()]
        if NEGATION_RE.search(preceding):
            continue
        return True
    return False


# Required-substring proxy for "the body carries the never-SPAWN clause" - the leaf/spawner
# invariant this pass exists to protect (snippets/worker-brief.md's leaf clause is the prose SSOT
# this mirrors: "cannot launch agents" / "HARD LEAF - never launches another agent"). Scoped to the
# never-SPAWN family ONLY, on purpose: git-abstention is a SEPARATE, independent guarantee already
# enforced repo-wide by tests/test_git_delegation_boundary.py, so folding git phrasings in here
# would let unrelated git-delegation boilerplate stand in for the never-spawn promise - the exact
# hole (17/26 leaves) that let a dropped never-spawn sentence pass strict. Several accepted spawn
# phrasings on purpose - agents that self-declare do not all share one exact wording.
NEVER_SPAWN_CLAUSE_RE = re.compile(
    r"(hard[- ]leaf|never launch(?:es)? (?:another|an|no) agent|launch(?:es)? no (?:sub-?)?agent"
    r"|does not (?:launch|spawn|invoke) (?:a |an |another )?(?:sub-?)?agent"
    r"|never spawns?(?: (?:a|an|another) (?:sub-?)?agent)?|no sub-?agents?"
    r"|cannot launch agents)",
    re.I,
)
SELF_REF_RE = re.compile(r"--([a-z0-9-]+)\s*:\s*var\(\s*--\1\b", re.I)
MACHINE_PATH_RE = re.compile(r"/(?:home|Users)/([A-Za-z0-9._-]+)/")
# Usernames that are NOT a leak of this machine's real home: doc placeholders + standard
# system/CI accounts (e.g. GitHub Actions runs under /home/runner, containers under /root).
PLACEHOLDER_USERS = {
    "user", "username", "you", "youruser", "your-user", "me", "name", "odoo",
    "runner", "root", "shared", "dev", "developer", "ci", "ubuntu", "vagrant", "app",
}


def _machine_path_leak(text: str) -> bool:
    """True if text contains a real (non-placeholder) absolute home path - a machine leak."""
    return any(u.lower() not in PLACEHOLDER_USERS for u in MACHINE_PATH_RE.findall(text))
HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b")
FENCE_RE = re.compile(r"```(scss|css|sass|less)\b(.*?)```", re.S)


def load_orch():
    data = json.loads(DEPS_FILE.read_text(encoding="utf-8"))
    return {k: v for k, v in data.get("orchestration", {}).items() if not k.startswith("_")}


def load_agents():
    data = json.loads(DEPS_FILE.read_text(encoding="utf-8"))
    return dict(data.get("agents", {}))


def skill_body(name: str) -> str | None:
    p = SKILLS_DIR / name / "SKILL.md"
    return p.read_text(encoding="utf-8") if p.exists() else None


def agent_body(name: str) -> str | None:
    p = AGENTS_DIR / f"{name}.md"
    return p.read_text(encoding="utf-8") if p.exists() else None


def check_agent_roles(findings: list[str]) -> None:
    """8. Agent-role SSOT lint (V-01 mechanism) - LIVE and enforcing (roles are populated).

    (c) Coverage: every agents/<name>.md on disk must declare a `role` in
        skill_tool_deps.json "agents"."<name>"."role" (mirrors the skill-side coverage pass,
        rule 1). A new agent file added without an SSOT role entry - or an entry with no `role`
        key - is a finding, so a wholly-unregistered agent can no longer slip through role-less.

    Then, reading `agents.<name>.role`: for `role == "leaf"`, asserts the agent body
    (a) carries the never-SPAWN clause (NEVER_SPAWN_CLAUSE_RE - scoped to the never-launch-an-agent
    family only; git-abstention is independently enforced by tests/test_git_delegation_boundary.py,
    so unrelated git-delegation boilerplate can no longer stand in for the never-spawn promise),
    (b) shows no positive spawn language (reuses `_has_positive_spawn` - the SAME detector rule 5
    uses, so there is one SSOT regex for "does this body launch an agent", not two), and (c) shows
    no positive git-mutation instruction.

    (Historically this pass shipped INERT while `role` was unpopulated; it now bites.)
    """
    agents = load_agents()

    # (c) Coverage - disk -> SSOT. Every agent that exists on disk must have a `role` in the map.
    on_disk = sorted(p.stem for p in AGENTS_DIR.glob("*.md")) if AGENTS_DIR.exists() else []
    for name in on_disk:
        if agents.get(name, {}).get("role") is None:
            findings.append(
                f"[agent-role] agents/{name}.md exists on disk but has no `role` in "
                f"skill_tool_deps.json's `agents` map"
            )

    for name in sorted(agents):
        entry = agents[name]
        role = entry.get("role")
        if role is None:
            continue  # role-less on-disk agents are flagged by the coverage pass above
        if role not in VALID_AGENT_ROLE:
            findings.append(
                f"[agent-role] '{name}' has invalid role '{role}' (not in {sorted(VALID_AGENT_ROLE)})"
            )
            continue
        if role != "leaf":
            continue  # only `leaf` carries a never-spawn/never-git obligation here
        body = agent_body(name)
        if body is None:
            findings.append(
                f"[agent-role] '{name}' has role=leaf in the SSOT but agents/{name}.md does not exist"
            )
            continue
        if not NEVER_SPAWN_CLAUSE_RE.search(body):
            findings.append(
                f"[agent-role] '{name}' has role=leaf but its body does not carry the "
                f"never-spawn clause (HARD LEAF / never launches another agent)"
            )
        if _has_positive_spawn(body):
            findings.append(
                f"[agent-role] '{name}' has role=leaf but body actively dispatches an agent"
            )
        if _has_positive_git_mutation(body):
            findings.append(
                f"[agent-role] '{name}' has role=leaf but body instructs a git mutation"
            )


# Spawner-tier contract set (M6, 12-design-final.md): a `role: leaf` agent launches nothing, so
# none of these bind it - see spawner-completion-contract.md's own "vacuously compliant" sentence.
# Matched as a BARE FILENAME (not a full path) so it catches a citation regardless of which
# relative prefix (snippets/, skills/_shared/) precedes it in a given body.
SPAWNER_TIER_FILES = (
    "spawner-completion-contract.md",
    "concurrency-guard.md",
)


def check_role_scope(findings: list[str]) -> None:
    """11. [role-scope] - data-driven from `agents.<name>.role` (V-01 SSOT), never a hardcoded
    name list. Two halves:

    (a) a `role: leaf` agent body may not cite any member of SPAWNER_TIER_FILES - it launches
        nothing, so the spawner-tier contracts do not bind it.
    (b) a `role: spawner|coordinator` agent body MUST cite `spawner-completion-contract.md` - it
        launches agents, so R3 (the completion-report addressing rule) binds it directly.

    Half (b)'s subject set (agents with role in {spawner, coordinator}) is asserted NON-EMPTY
    before the check runs, so the half can never pass vacuously (an empty subject set would
    silently produce zero findings and look identical to "every spawner complies"). If a tree
    genuinely has no spawner/coordinator agent, set the top-level registry flag
    `_role_scope_no_spawners_expected: true` to make that an explicit, reviewable choice instead
    of a silent gap.
    """
    data = json.loads(DEPS_FILE.read_text(encoding="utf-8"))
    agents = data.get("agents", {})
    no_spawners_expected = bool(data.get("_role_scope_no_spawners_expected"))

    leaves = sorted(n for n, e in agents.items() if e.get("role") == "leaf")
    spawners = sorted(n for n, e in agents.items() if e.get("role") in ("spawner", "coordinator"))

    # (a) leaves may not cite the spawner-tier set.
    for name in leaves:
        body = agent_body(name)
        if body is None:
            continue  # coverage gap already reported by check_agent_roles
        for banned in SPAWNER_TIER_FILES:
            if banned in body:
                findings.append(
                    f"[role-scope] '{name}' has role=leaf but its body cites '{banned}' "
                    f"(spawner-tier contract) - a leaf launches nothing, so this does not bind it"
                )

    # (b) the spawner/coordinator subject set must be non-empty, or the check is vacuous.
    if not spawners:
        if not no_spawners_expected:
            findings.append(
                "[role-scope] subject set for the spawner-completion-contract.md citation check "
                "(agents with role in {spawner, coordinator}) is EMPTY - this would let half (b) "
                "of the rule pass vacyously. If no spawner/coordinator agent is genuinely expected, "
                "set the top-level registry flag `_role_scope_no_spawners_expected: true` to make "
                "that explicit; otherwise this is a real coverage gap."
            )
        return

    for name in spawners:
        body = agent_body(name)
        if body is None:
            findings.append(
                f"[role-scope] '{name}' has role={agents[name].get('role')!r} in the SSOT but "
                f"agents/{name}.md does not exist"
            )
            continue
        if "spawner-completion-contract.md" not in body:
            findings.append(
                f"[role-scope] '{name}' has role={agents[name].get('role')!r} but its body never "
                f"cites spawner-completion-contract.md - a spawner/coordinator launches agents, so "
                f"R3's completion-report addressing rule binds it directly"
            )


# Fenced ``` code blocks - the literal dispatch-prompt template a skill hands its agent. Scoping
# the [brief-fields] key search to these (not the whole SKILL.md prose) matches what the rule is
# actually checking: does the skill's OWN dispatch template emit this key, not merely mention it
# somewhere in surrounding explanation.
FENCE_BLOCK_RE = re.compile(r"```.*?```", re.S)


def agent_spawn_edges() -> dict[str, list[str]]:
    """Declared agent->agent dispatch edges, from `agents.<name>.spawns_agents`.

    A coordinator agent that re-briefs leaves of its own is the DISPATCHER of those leaves' briefs;
    the skill above it never writes them. Without this axis the whole agent->agent tier is invisible
    to [brief-fields] - a required key travelling only that tier is checked by nothing at all."""
    return {
        name: list(entry["spawns_agents"])
        for name, entry in load_agents().items()
        if isinstance(entry, dict) and entry.get("spawns_agents")
    }


def _brief_required(agents: dict, agent_name: str) -> list[str]:
    return ((agents.get(agent_name) or {}).get("brief") or {}).get("required") or []


def _dispatch_fences(body: str | None) -> str:
    return "\n".join(m.group(0) for m in FENCE_BLOCK_RE.finditer(body or ""))


def check_brief_fields(warn_only_findings: list[str]) -> None:
    """12. [brief-fields] - WARN-ONLY, PERMANENTLY (see module docstring). For every dispatch edge,
    report any key in `agents.<agent>.brief.required` that never appears inside the DISPATCHER's own
    dispatch fences. Never gates --strict/ORCH_STRICT, no matter how many findings - this is a
    permanent diagnostic, not a migration-window rule (contrast rules 9-10).

    Two edge tiers, because a brief is written by whoever actually fills it:

      skill -> agent   `orchestration.<skill>.spawns_agents`, MINUS every agent that a coordinator
                       in that same list dispatches. That field is a REACHABILITY set (it feeds the
                       generated ORCHESTRATION-MAP), so a leaf sitting under a coordinator appears
                       there even though the skill never writes that leaf's brief. Charging the
                       skill for it produces a finding no edit to the skill can ever clear.
      agent -> agent   `agents.<dispatcher>.spawns_agents` - the tier where a coordinator's own
                       leaf briefs live, checked against the coordinator's body fences."""
    orch = load_orch()
    agents = load_agents()
    edges = agent_spawn_edges()

    for skill_name in sorted(orch):
        spawns_agents = (orch[skill_name] or {}).get("spawns_agents") or []
        if not spawns_agents:
            continue
        delegated = {leaf for a in spawns_agents for leaf in edges.get(a, ())}
        fences = _dispatch_fences(skill_body(skill_name))
        for agent_name in spawns_agents:
            if agent_name in delegated:
                continue  # a coordinator in this same list writes that brief - checked below
            for key in _brief_required(agents, agent_name):
                if key not in fences:
                    warn_only_findings.append(
                        f"[brief-fields] '{skill_name}' dispatches '{agent_name}' but its "
                        f"dispatch fences never emit required key '{key}' "
                        f"(agents.{agent_name}.brief.required)"
                    )

    for dispatcher in sorted(edges):
        body = agent_body(dispatcher)
        if body is None:
            warn_only_findings.append(
                f"[brief-fields] '{dispatcher}' declares spawns_agents in the SSOT but "
                f"agents/{dispatcher}.md does not exist"
            )
            continue
        fences = _dispatch_fences(body)
        for agent_name in edges[dispatcher]:
            for key in _brief_required(agents, agent_name):
                if key not in fences:
                    warn_only_findings.append(
                        f"[brief-fields] agent '{dispatcher}' dispatches '{agent_name}' but its "
                        f"dispatch fences never emit required key '{key}' "
                        f"(agents.{agent_name}.brief.required)"
                    )


# --- [wait-scope] / [wait-mechanism] (M1 guard - rules 9/10, WARN-FIRST for one release) -------
#
# Ground truth (R0, spawner-completion-contract.md): a subagent CAN launch a child and CAN block on
# its result (a blocking Agent-tool launch, `run_in_background: false`), and MUST whenever it needs
# that result. Only the ROOT conversation is resumed when a background child finishes - a launcher
# that is itself dispatched is never woken by its own child - so "launch async and END ITS TURN to
# be resumed" is a root-only branch, and taking it below the root is a permanent stall, not a
# slower path. The hazards this pair detects are: an unattributed park instruction (a reader cannot
# tell which R0 branch it exercises, so nothing reveals whether the park is even reachable there),
# uncommitted work surviving a turn boundary, a poll/sleep loop standing in for the mechanical
# barrier a blocking launch already provides, and a dispatch claim made with no visible check that
# the launching capability exists in the first place.
#
# [wait-scope] (rule 9) - a park/wait instruction (end turn / park / hold until / wait to be
# resumed / await) near turn/child/worker/agent vocabulary, anywhere under skills/*/SKILL.md,
# agents/*.md, snippets/*.md, is a finding when its enclosing section:
#   (a) names no R0 branch - no R0/move-N/run_in_background/NEEDS_NEXT/nesting-cap/
#       spawner-completion-contract.md citation - so a reader cannot tell whether this is a
#       blocking launch, a root-only async park, or the no-capability branch; or
#   (b) shows file-writing language (write/author/edit) with no commit/checkpoint safeguard
#       stated nearby - the non-interactive-surface bound R0 itself names: never end a turn with
#       uncommitted work.
#
# [wait-mechanism] (rule 10) - two independent detectors, neither ever correct under any R0
# branch:
#   (a) an instruction to POLL or SLEEP while waiting for a child - a blocking launch already
#       blocks the call itself, and a root-only async launch parks via end-of-turn; nothing
#       legitimately polls or sleeps FOR a child's completion. A periodic task-list check is a
#       DIFFERENT, sanctioned pattern (status tracking, not a busy-wait loop) and is excluded.
#   (b) a claim that a dispatch happened (launch/dispatch/invoke the Agent tool) with no nearby
#       capability-handling language (own toolset / Agent tool absent / nesting cap / R0 /
#       NEEDS_NEXT) - R0 move 1 requires checking your own toolset FIRST, so an unattended dispatch
#       claim reads as though the Agent tool is always assumed present.
#
# Both are proximity/citation-based (not a full semantic read), so a legitimate instruction worded
# unusually can still false-positive - exactly why they ship WARN-FIRST for one release: findings
# from these two rules are collected into a SEPARATE list and never flip the exit code, even under
# --strict/ORCH_STRICT - only the 8 rules above (and the agent-role pass) gate the strict exit.
# This mirrors the whole-script migration pattern this file already documents at its own top
# (WARN-FIRST docstring, line ~31): ship loud-but-inert, then flip to enforcing once the tree is
# clean. Flip these two to strict-gating in the release after this one lands.

WAIT_VERB_RE = re.compile(
    r"(END your turn|end the turn|\bpark\b|hold until|wait to be resumed|\bawait\b)",
    re.I,
)
WAIT_SCOPE_CONTEXT_RE = re.compile(r"\b(turn|child|worker|agent)\b", re.I)
H2_RE = re.compile(r"^##\s+(.*)$", re.M)
LAUNCH_VERB_RE = re.compile(r"\b(launch|dispatch|spawn|Agent tool)\b", re.I)

# R0-branch attribution: any citation proving the instruction states WHICH branch it belongs to
# (move 1 no-capability / move 2 blocking-launch / move 3 async-park), or a pointer to the R0 SSOT
# itself.
R0_BRANCH_CITE_RE = re.compile(
    r"\bR0\b|move\s*[123]\b|run_in_background|NEEDS_NEXT|nesting cap|"
    r"spawner-completion-contract\.md",
    re.I,
)
# Uncommitted-work bound: a section that shows file-writing language must also show SOME
# commit/checkpoint safeguard, per R0's own non-interactive-surface rule.
WRITE_CONTEXT_RE = re.compile(r"\bwrit(?:e|es|ing|ten)\b|\bauthor(?:s|ed|ing)?\b|\bedit(?:s|ed|ing)?\b", re.I)
COMMIT_SAFEGUARD_RE = re.compile(r"\bcommit(?:ted|s|ting)?\b|\bcheckpoint\b|uncommitted work", re.I)

# [wait-mechanism] (a): poll/sleep paired with wait-for-a-child vocabulary, excluding the
# sanctioned task-list status check (task-list polling is status tracking, not a
# busy-wait loop standing in for the mechanical barrier).
POLL_SLEEP_RE = re.compile(r"\bpoll(?:s|ing|ed)?\b|\bsleep\b", re.I)
TASK_LIST_RE = re.compile(r"task list|task-list|checklist", re.I)
# [wait-mechanism] (b): a dispatch claim with no nearby capability-handling language.
DISPATCH_CLAIM_RE = re.compile(
    r"(invoke the Agent tool|call the Agent tool"
    r"|dispatch(?:es)? (?:to )?the `?[a-z][a-z-]+`? agent"
    r"|launch(?:es|ing)? (?:the )?`?[a-z][a-z-]+`? agent)",
    re.I,
)
CAP_HANDLING_RE = re.compile(
    r"own toolset|Agent tool (?:is|is not|absent|has|exposes)|nesting cap|no Agent tool|"
    r"capability (?:is )?absent|NEEDS_NEXT|\bR0\b",
    re.I,
)
# Reuses the same lookback-negation convention as _has_positive_spawn/_has_positive_git_mutation
# above (module-level NEGATION_RE) so "do not poll" / "never sleep" are never flagged as if they
# were positive instructions to poll/sleep.


def _enclosing_h2(text: str, pos: int) -> str:
    """The H2 heading text whose section contains offset `pos` ('' if none precede it)."""
    heading = ""
    for m in H2_RE.finditer(text):
        if m.start() > pos:
            break
        heading = m.group(1)
    return heading


def _wait_scope_scan_files() -> list[Path]:
    files = sorted(SNIPPETS_DIR.glob("*.md")) if SNIPPETS_DIR.exists() else []
    files += sorted(SKILLS_DIR.rglob("SKILL.md")) if SKILLS_DIR.exists() else []
    files += sorted(AGENTS_DIR.glob("*.md")) if AGENTS_DIR.exists() else []
    return files


def _wait_instructions(text: str):
    """Yield (match, heading, section_text) for each park-the-turn verb sitting near
    turn/child/worker/agent vocabulary (a 200-char window on each side - a wait verb far from
    that vocabulary is not a spawner-completion concern, e.g. 'await confirmation from the
    user')."""
    for m in WAIT_VERB_RE.finditer(text):
        window = text[max(0, m.start() - 200): m.start() + 200]
        if not WAIT_SCOPE_CONTEXT_RE.search(window):
            continue
        heading = _enclosing_h2(text, m.start())
        section_start = text.rfind("\n## ", 0, m.start())
        section_text = text[max(0, section_start):m.start()]
        yield m, heading, section_text


def check_wait_scope(warn_only_findings: list[str]) -> None:
    """[wait-scope] (rule 9) - see module-level note above. A park/wait instruction is a finding
    when its section names no R0 branch, OR shows file-writing language with no stated commit/
    checkpoint safeguard (the two real hazards; a bare park instruction is not itself one)."""
    for f in _wait_scope_scan_files():
        text = f.read_text(encoding="utf-8")
        rel = f.relative_to(PLUGIN_ROOT)
        for m, heading, section_text in _wait_instructions(text):
            if not R0_BRANCH_CITE_RE.search(section_text):
                warn_only_findings.append(
                    f"[wait-scope] {rel}: {m.group()!r} park/wait instruction names no R0 branch "
                    f"(no R0/move-N/run_in_background/NEEDS_NEXT/nesting-cap/"
                    f"spawner-completion-contract.md citation in its section, heading: {heading!r})"
                )
            if WRITE_CONTEXT_RE.search(section_text) and not COMMIT_SAFEGUARD_RE.search(section_text):
                warn_only_findings.append(
                    f"[wait-scope] {rel}: {m.group()!r} sits in a section with file-writing "
                    f"language but no stated commit/checkpoint safeguard - risks ending a turn "
                    f"with uncommitted work (heading: {heading!r})"
                )


def check_wait_mechanism(warn_only_findings: list[str]) -> None:
    """[wait-mechanism] (rule 10) - see module-level note above. Two detectors: (a) poll/sleep
    paired with wait-for-a-child vocabulary (excluding a sanctioned own-task-list check), and
    (b) a dispatch claim with no nearby capability-handling language."""
    for f in _wait_scope_scan_files():
        text = f.read_text(encoding="utf-8")
        lines = text.splitlines()
        rel = f.relative_to(PLUGIN_ROOT)

        # (a) poll/sleep while waiting for a child.
        for i, line in enumerate(lines):
            for m in POLL_SLEEP_RE.finditer(line):
                preceding = line[max(0, m.start() - 45):m.start()]
                if NEGATION_RE.search(preceding):
                    continue  # "do not poll" / "never sleep" - a prohibition, not an instruction
                window = "\n".join(lines[max(0, i - 3): i + 4])
                if TASK_LIST_RE.search(window):
                    continue  # sanctioned task-list status check, not a busy-wait loop
                if WAIT_SCOPE_CONTEXT_RE.search(window):
                    warn_only_findings.append(
                        f"[wait-mechanism] {rel}:{i + 1}: {m.group()!r} instructs polling/"
                        f"sleeping near wait-for-a-child vocabulary - never correct under any R0 "
                        f"branch (a blocking launch already blocks; an async launch parks via "
                        f"end-of-turn, never a poll/sleep loop)"
                    )

        # (b) a dispatch claim with no nearby capability-handling language.
        for m in DISPATCH_CLAIM_RE.finditer(text):
            preceding = text[max(0, m.start() - 45):m.start()]
            if NEGATION_RE.search(preceding):
                continue  # "does not launch the X agent" - a self-declared leaf, not a claim
            window = text[max(0, m.start() - 300): m.start() + 300]
            if not CAP_HANDLING_RE.search(window):
                line_no = text.count("\n", 0, m.start()) + 1
                warn_only_findings.append(
                    f"[wait-mechanism] {rel}:{line_no}: {m.group()!r} claims a dispatch with no "
                    f"nearby capability-handling language (own toolset / Agent tool absent / "
                    f"nesting cap / R0 / NEEDS_NEXT) - R0 move 1 requires checking your own "
                    f"toolset before every launch"
                )


# --- [card-budget] (rule 13, M9) --------------------------------------------------------------

CARD_BUDGET_GRANDFATHER_FILE = REPO_ROOT / "tests" / "fixtures" / "card_budget_grandfather.json"
CARD_BUDGET_DEFAULT_CAP = 4096
CARD_BUDGET_MIN_CITERS = 3


def _card_budget_candidates() -> list[Path]:
    """Every `snippets/*.md` + `skills/_shared/*.md` file - the shared-contract corpus a hot cold
    context might load repeatedly - PLUS every path carrying an explicit budget entry in the
    grandfather file, wherever it lives.

    The >=3-citer count is a DISCOVERY heuristic for "this shared file is hot"; an explicit budget
    entry is a DECLARATION of the same fact, so it is an entry ticket in its own right. That second
    door is the only way in for a hot contract the heuristic structurally cannot see - notably a
    top-level `skills/<name>/SKILL.md` runtime contract, whose basename `SKILL.md` is shared by
    every skill and so makes any basename-keyed citer count meaningless.

    `snippets/references/*.md` is excluded on purpose: per M9/[ref-scope], no consumer-facing file
    may ever cite it, so it can never reach the >=3-citer threshold and including it would only
    slow the scan."""
    files = list(SNIPPETS_DIR.glob("*.md"))
    if SHARED_DIR.exists():
        files += list(SHARED_DIR.glob("*.md"))
    files = [f for f in files if f.parent != REFERENCES_DIR]
    files += [
        p for p in (PLUGIN_ROOT / rel for rel in _load_card_budget_grandfather()) if p.is_file()
    ]
    return sorted(set(files))


def _consumer_bodies() -> dict[Path, str]:
    """Every `skills/*/SKILL.md` + `agents/*.md` body, read once and reused for every candidate's
    citer count (avoids an O(candidates x consumers) re-read of the same ~130 files)."""
    files = list(SKILLS_DIR.rglob("SKILL.md"))
    if AGENTS_DIR.exists():
        files += list(AGENTS_DIR.glob("*.md"))
    return {f: f.read_text(encoding="utf-8") for f in files}


def _load_card_budget_grandfather() -> dict[str, int]:
    if not CARD_BUDGET_GRANDFATHER_FILE.is_file():
        return {}
    data = json.loads(CARD_BUDGET_GRANDFATHER_FILE.read_text(encoding="utf-8"))
    return dict(data.get("budgets", {}))


def check_card_budget(findings: list[str]) -> None:
    """13. [card-budget] - see module docstring. Data-driven, two ways a file qualifies:
    (a) it carries an explicit grandfather entry - the declaration IS the qualification, and its
    budget is that entry; or (b) >=3 distinct skills+agents cite its basename, and its budget is
    the default cap. Fires only on a size that exceeds that budget."""
    bodies = _consumer_bodies()
    grandfather = _load_card_budget_grandfather()
    for cand in sorted(_card_budget_candidates()):
        relpath = str(cand.relative_to(PLUGIN_ROOT))
        if relpath in grandfather:
            budget = grandfather[relpath]
            why = "declared hot contract - explicit budget entry"
        else:
            citers = sum(1 for text in bodies.values() if cand.name in text)
            if citers < CARD_BUDGET_MIN_CITERS:
                continue
            budget = CARD_BUDGET_DEFAULT_CAP
            why = (
                f"cited by {citers} skills/agents, >= the {CARD_BUDGET_MIN_CITERS}-citer threshold"
            )
        size = cand.stat().st_size
        if size > budget:
            findings.append(
                f"[card-budget] '{relpath}' is {size}B, over its budget of {budget}B "
                f"({why}) - grow it only with a deliberate grandfather-file bump, never silently"
            )


# --- [ref-scope] (rule 14, M9) ----------------------------------------------------------------

# A real relative path (>=1 '/' before the final segment), optionally prefixed by the plugin-root
# token - deliberately excludes a bare `SKILL.md`/`file.md` mention, which would collide every
# skill's own same-named file with an unrelated oversize one.
LARGE_FILE_CITE_RE = re.compile(
    r"(?:\$\{CLAUDE_PLUGIN_ROOT\}/)?([A-Za-z0-9_-]+(?:/[A-Za-z0-9_.-]+)+\.md)"
)
LARGE_FILE_THRESHOLD = 20480
SECTION_ANCHOR_CHARS = "§"
REF_SCOPE_WINDOW = 150
REFERENCES_PATH_SUBSTRING = "snippets/references/"


def check_ref_scope_citation_anchor(warn_only_findings: list[str]) -> None:
    """14a. [ref-scope] half (a) - WARN-ONLY FOR ONE RELEASE (see module docstring rationale below).
    A SKILL.md/agents/*.md body citing another real file over the size threshold should carry a
    '§ <anchor>' within REF_SCOPE_WINDOW chars of the citation - a whole-file citation for one
    clause is exactly the X-64 pattern this half exists to catch.

    Ships warn-first: the mechanism is new (this wave) and the measured real-tree backlog (81
    findings across ~20 files, dominated by two non-wave-7 files - odoo-frontend-fidelity.md and
    visual-evidence-lifecycle-contract.md, neither named by the design as requiring an immediate
    sweep) is large enough that a hasty blanket anchor-add risks placing a MEANINGLESS anchor
    (worse than none - it would look precise without being precise) at sites this wave did not
    have time to individually verify. The three sites the design explicitly named (X-64:
    agents/odoo-coder.md citing skills/odoo-instance/SKILL.md and skills/odoo-forward-port/SKILL.md;
    skills/odoo-coding/SKILL.md citing docs/reference/workflow-harness.md) are already anchored.
    Mirrors the exact precedent this file already sets for rules 9/10 (a new proximity-based rule
    with a real pre-existing backlog ships loud-but-inert, then flips to strict once the tree is
    swept clean - see check_wait_scope/check_wait_mechanism above)."""
    consumer_files = list(SKILLS_DIR.rglob("SKILL.md"))
    if AGENTS_DIR.exists():
        consumer_files += list(AGENTS_DIR.glob("*.md"))

    for f in consumer_files:
        text = f.read_text(encoding="utf-8")
        rel = f.relative_to(PLUGIN_ROOT)
        for m in LARGE_FILE_CITE_RE.finditer(text):
            cited_rel = m.group(1)
            candidate = PLUGIN_ROOT / cited_rel
            if not candidate.is_file():
                continue
            if candidate.resolve() == f.resolve():
                continue  # self-citation (a file's own header pointing at itself) is not a load
            size = candidate.stat().st_size
            if size <= LARGE_FILE_THRESHOLD:
                continue
            window = text[max(0, m.start() - REF_SCOPE_WINDOW): m.start() + REF_SCOPE_WINDOW]
            if SECTION_ANCHOR_CHARS not in window:
                line_no = text.count("\n", 0, m.start()) + 1
                warn_only_findings.append(
                    f"[ref-scope] {rel}:{line_no} cites '{cited_rel}' ({size}B, over the "
                    f"{LARGE_FILE_THRESHOLD}B threshold) with no '§ <anchor>' within "
                    f"{REF_SCOPE_WINDOW} chars"
                )


def check_ref_scope_no_reference_pointer(findings: list[str]) -> None:
    """14b. [ref-scope] half (b) - LIVE and enforcing (part of `findings`, gates --strict). No
    skills/agents/snippets file may name the 'snippets/references/' path shape at all - the
    read-both hazard closure at the heart of M9's safety design: an executing agent must never be
    handed a pointer to the reference sibling it could follow instead of the (now-inverted)
    decidable rule file. Scanned over the agent-facing corpus MINUS docs/ - docs/ is exempt because
    the reference tree is meant to stay discoverable from docs/authoring-skills-and-agents.md and
    from this lint, by design; commands/ and workflows/ ARE in scope (an agent reads them in
    full)."""
    for f in agent_facing_files(include_docs=False):
        text = f.read_text(encoding="utf-8")
        rel = f.relative_to(PLUGIN_ROOT)
        if REFERENCES_PATH_SUBSTRING in text:
            findings.append(
                f"[ref-scope] {rel} names the '{REFERENCES_PATH_SUBSTRING}' path - a "
                f"consumer-facing file must never be handed a pointer to a reference sibling it "
                f"could read-both instead of the decidable rule"
            )


# --- [no-provenance] (rule 15, M10, X-50) -------------------------------------------------------

# PLUGIN-SELF provenance vocabulary. Three families, one union:
#   (a) the internal design tags - `(V-NN)` uses two-or-more digits so an Odoo version string
#       (e.g. "v8") can never collide, and `(Problem N)`;
#   (b) the changelog phrasing a rewrite leaves behind - `Replaces ` is deliberately CASE-SENSITIVE
#       (`(?-i:...)`) because the capitalized sentence-opener is the changelog shape, while a
#       lower-case mid-sentence "replaces" is ordinary prose ("v19 replaces the server flags");
#       `since 4.` / `new in 4.` require a following digit so they mean THIS plugin's 4.x line;
#   (c) issue/PR references - a bare `#\d+` is unusable (it collides with `ETHOS #10`, `Gate #1`,
#       a hex colour, a markdown anchor), so the reference must be QUALIFIED by issue/PR/ticket/
#       bug/GH vocabulary, plus the two bare provenance phrasings `see PR` / `tracked in`.
# `\bsee PR\b` needs its word boundary: without it, "See prose below" matches.
NO_PROVENANCE_RE = re.compile(
    r"\(V-\d{2,}[^)]*\)"
    r"|\(Problem \d+\)"
    r"|(?-i:\bReplaces\s)"
    r"|\bformerly\b"
    r"|\brenamed from\b"
    r"|\bwas previously\b"
    r"|\bas of version\b"
    r"|\bsince 4\.\d"
    r"|\bnew in 4\.\d"
    r"|\bdeprecated in fav(?:ou)?r of\b"
    r"|\blegacy\s"
    r"|\bno longer exists\b"
    r"|\bmoved here from\b"
    r"|\boriginally lived in\b"
    r"|\bconsolidated from\b"
    r"|\bsee PR\b"
    r"|\btracked in\b"
    r"|\b(?:issues?|PRs?|pull[- ]requests?|tickets?|bugs?|GH)\s*#\d+",
    re.I,
)

# THE DISCRIMINATOR every guard below approximates: RESIDUE narrates what THIS PLUGIN used to do
# (worthless to an executing agent, and free to delete - git already has it). OPERATIVE text tells
# the agent what to DO about something that still exists (a lease field the allocator still reads,
# a `SUGGESTED_NEXT:` line the parser still accepts, a prospect's incumbent POS, an Odoo CSS era) -
# deleting that BREAKS a live consumer. Same vocabulary, opposite value; the guards split them.

# Guard 1 - ODOO DOMAIN version history is legitimate, load-bearing knowledge, never residue.
# An Odoo version anchor: a real Odoo major series (8..29 - a bare `v0.5` or `v3` is therefore NOT
# one), the series notation `17.0`, a `saas-` build, the explicit "Odoo version/series/era"
# phrasing the generated tool-surface blurb uses ("spanning every indexed Odoo version (legacy
# through latest)"), or a PARAMETERIZED series placeholder (`<src-series>`, "the target series") -
# a series named by ROLE instead of by number is still a series, and the forward-port /
# modules-upgrade corpus names them that way throughout.
ODOO_VERSION_ANCHOR_RE = re.compile(
    r"\bOdoo[\s-]*(?:[89]|1\d|2\d)\b"
    r"|\bOdoo[\s-]*(?:versions?|series|majors?|releases?|eras?)\b"
    r"|\bv(?:[89]|1\d|2\d)(?:\.\d)?\b"
    r"|\b(?:[89]|1\d|2\d)\.0\b"
    r"|\bsaas[-~]\d"
    r"|\b(?:src|tgt|source|target)[-\s]series\b",
    re.I,
)
# Guard 1b - Odoo FRAMEWORK-ERA idioms. "legacy `web.Widget`" / "legacy widgets" / "legacy AMD" /
# "legacy `oe_*` classes" name Odoo's own frontend eras; the adjective there is domain vocabulary,
# not self-history.
ODOO_ERA_IDIOM_RE = re.compile(
    r"\b(?:OWL|AMD|QWeb|QUnit|Hoot|SCSS|LESS|widgets?)\b|odoo\.define|web\.Widget|@api\."
    r"|\boe_[a-z*]",
    re.I,
)
# Guard 1c - INCUMBENT-SYSTEM vocabulary. In the sales/discovery corpus `legacy` names the
# PROSPECT's pre-Odoo system - their POS, their accounting package, the format their history has to
# be migrated out of. Recording that is the entire point of a discovery profile; it is the
# customer's history, never this plugin's.
INCUMBENT_SYSTEM_RE = re.compile(
    r"\bcurrent system\b"
    r"|\bdata migration\b"
    r"|\bincumbent\b"
    r"|\bspreadsheets?\b"
    r"|\bExcel\b"
    r"|\bPOS\b"
    r"|\bERP\b"
    r"|\baccounting (?:software|system|package|migration)\b",
    re.I,
)
# Guard 1d - CODE-UNDER-WORK evolution. `legacy` / `no longer exists` often describe the codebase
# the agent OPERATES ON, not this plugin: Odoo core absorbing a custom feature, or a rebase base
# whose design superseded the commit being replayed. Those are findings the agent MUST state.
# `core` is matched without a leading `\b` so `absorbing_core_feature` counts.
CODE_UNDER_WORK_RE = re.compile(
    r"\b(?:target|upstream|Odoo)[-\s]core\b"
    r"|(?<![A-Za-z0-9])core[ _-](?:features?|modules?|mechanisms?|APIs?|computes?|fields?|behaviou?rs?)\b"
    r"|\bcore absorbed\b"
    r"|\bbase (?:HEAD|branch|tip|design|idioms?)\b",
    re.I,
)
DOMAIN_ANCHOR_RES = (
    ODOO_VERSION_ANCHOR_RE,
    ODOO_ERA_IDIOM_RE,
    INCUMBENT_SYSTEM_RE,
    CODE_UNDER_WORK_RE,
)
# Guard 1e - DEFINED-TERM anaphora. A document that DEFINES a legacy ERA in a heading carrying an
# Odoo version anchor (`## Legacy v8-v14 workflow`) uses a later bare `legacy` as a back-reference
# to that defined term ("same as the legacy Round 5"), not as a claim about its own past. Only the
# bare `legacy` token is anaphoric this way - every other alternative still fires in such a file.
LEGACY_ERA_HEADING_RE = re.compile(r"^#{1,6} +.*\blegacy\b.*$", re.I | re.M)
# Guard 3 - OPERATIVE BACK-COMPAT. A back-compat instruction has a LIVE consumer (the allocator
# still reads `owner.session_id`; the continuation parser still accepts `SUGGESTED_NEXT:`), so it
# is a rule, not a memoir - deleting it breaks the reader. Detected by the handling vocabulary such
# an instruction cannot be phrased without: an explicit back-compat/fallback label, or a verb
# applied TO the old shape ("is still read", "treats ... as", "skips the stop", "maps to").
# `fallback` must head a noun phrase ("as a fallback", "its `session_id` fallback") so an unrelated
# "there is no hard fallback locale" cannot launder a finding.
OPERATIVE_BACKCOMPAT_RE = re.compile(
    r"\bback[- ]?compat"
    r"|\bbackwards?[- ]compatib"
    r"|\b(?:as an?|its|the)\s+(?:\S+\s+){0,3}fallback\b"
    r"|\bfalls? back\b"
    r"|\bread (?:only )?as\b"
    r"|\btreats?\b"
    r"|\btreated as\b"
    r"|\bskips?\b"
    r"|\bmaps? to\b"
    r"|\bstill (?:read|accepted|honou?red|supported|works?|valid|parsed|handled|fires|recogni\w+)\b",
    re.I,
)
# Which alternatives guard 3 may exempt: only vocabulary that CAN name a still-live old artifact.
# A pure provenance tag (`(V-34)`, `see PR #12`, `since 4.2`) can never BE an operative
# instruction, so nearby back-compat wording must never launder it.
BACKCOMPAT_ELIGIBLE_RE = re.compile(
    r"\blegacy\b"
    r"|\bno longer exists\b"
    r"|\bformerly\b"
    r"|\brenamed from\b"
    r"|\bwas previously\b"
    r"|\bdeprecated in fav",
    re.I,
)
# How far around a match to look for the domain signal. One sentence-ish on each side: wide enough
# that "renamed from `test_pylint` at v13" is read as one statement, narrow enough that an
# unrelated version string three paragraphs away cannot launder a real finding.
PROVENANCE_DOMAIN_WINDOW = 160


def _match_window(text: str, start: int, end: int) -> str:
    return text[max(0, start - PROVENANCE_DOMAIN_WINDOW): end + PROVENANCE_DOMAIN_WINDOW]


def _is_domain_context(text: str, start: int, end: int) -> bool:
    """True if the match is talking about a domain OUTSIDE this plugin - Odoo's own version/era
    history, the prospect's incumbent system, or the codebase under work - not this plugin's past."""
    window = _match_window(text, start, end)
    return any(rx.search(window) for rx in DOMAIN_ANCHOR_RES)


def _is_operative_backcompat(text: str, start: int, end: int) -> bool:
    """True if the window reads as a LIVE handling instruction for an old-but-still-extant shape
    (guard 3) rather than a narration of what this plugin used to do."""
    return bool(OPERATIVE_BACKCOMPAT_RE.search(_match_window(text, start, end)))


def _defines_legacy_era(text: str) -> bool:
    """True if the file itself defines `legacy` as an Odoo ERA in a heading (guard 1e)."""
    return any(ODOO_VERSION_ANCHOR_RE.search(h) for h in LEGACY_ERA_HEADING_RE.findall(text))


def _inside_quoted_example(text: str, pos: int) -> bool:
    """True if `pos` sits inside a double-quoted span - a QUOTED EXAMPLE (a user utterance in a
    routing trigger list, a literal string), which is never the file asserting its own history.
    Parity is counted from the start of the enclosing blank-line-delimited block so a wrapped YAML
    `description:` or a multi-row trigger table is measured as one unit."""
    block_start = text.rfind("\n\n", 0, pos) + 2
    return text.count('"', block_start, pos) % 2 == 1


def check_no_provenance(findings: list[str]) -> None:
    """15. [no-provenance] - see module docstring. Agent-facing prose carries no PLUGIN-SELF
    changelog / issue-tracking provenance (`(V-34)`, `Replaces X`, `legacy <old name of ours>`,
    `see PR #12`, ...) - that history belongs in git, not in the per-invocation path. What passes:
    DOMAIN history (guards 1/1b/1c/1d), a legacy era the document itself defines (1e), a quoted
    example (2), and an OPERATIVE back-compat instruction about a shape that still exists (3)."""
    for f in agent_facing_files():
        text = f.read_text(encoding="utf-8")
        rel = f.relative_to(PLUGIN_ROOT)
        legacy_era_file = _defines_legacy_era(text)
        for m in NO_PROVENANCE_RE.finditer(text):
            token = m.group()
            if _is_domain_context(text, m.start(), m.end()):
                continue
            if _inside_quoted_example(text, m.start()):
                continue
            if BACKCOMPAT_ELIGIBLE_RE.search(token) and _is_operative_backcompat(text, m.start(), m.end()):
                continue
            if legacy_era_file and token.strip().lower() == "legacy":
                continue
            line_no = text.count("\n", 0, m.start()) + 1
            findings.append(f"[no-provenance] {rel}:{line_no}: {token!r}")


# --- [instance-truth] (rule 16) ---------------------------------------------------------------
#
# `instance_touching` is the one registry field the lint used to validate ONLY against its own
# derivation: `_derive_gate_tier` reads it, and rule 1d then asserts the stored tier equals what
# that derivation produced. A wrong input therefore produced a self-consistent wrong output and a
# green suite - a chat-only skill could declare `true`, derive `L2`, and stop every automatic run
# to authorize an irreversible act it never performs. This rule reads the SKILL.md body instead,
# so the registry can be CONTRADICTED.
#
# The generated `## MCP tools` region is cut out first. It is emitted from the tool surface, and
# its `cli_help` blurb names `odoo-bin` for skills that never touch an instance - a naive scan
# would read that as corroboration of exactly the false declarations this rule exists to catch.

GENERATED_TOOLS_RE = re.compile(
    r"<!-- BEGIN GENERATED TOOLS -->.*?<!-- END GENERATED TOOLS -->", re.S
)
# STRONG evidence: an ACT, not a mention. Either the allocator lease API (you cannot heartbeat or
# release a lease you do not hold), or an active dispatch of the instance front door.
INSTANCE_LEASE_CALL_RE = re.compile(
    r"allocator\.py\s+`?(?:acquire|release|heartbeat|status)\b", re.I
)
INSTANCE_FRONT_DOOR_RE = re.compile(r"`?odoo-instance(?:-ops)?`?", re.I)
# A dispatch verb (or the Skill-tool phrasing) near the front door. `Skill(` catches the
# `Skill(odoo-instance)` call form the coding corpus uses.
INSTANCE_DISPATCH_VERB_RE = re.compile(
    r"\b(dispatch(?:es|ing)?|invok(?:e|es|ing)|launch(?:es|ing)?|tell|re-invoke)\b"
    r"|Skill\(|via the Skill tool",
    re.I,
)
# Hand-off vocabulary. A line that ROUTES the instance need elsewhere is the opposite of driving
# one - it is the shape `odoo-qa-suite` uses (`NEEDS_NEXT -> odoo-instance`) and the shape every
# Out-of-Scope row uses, so a front-door mention on such a line is never evidence.
INSTANCE_ROUTE_AWAY_RE = re.compile(
    r"NEEDS_NEXT|routes? to|route to|Route instead|install first via|delegated via", re.I
)
INSTANCE_DISPATCH_WINDOW = 90
# WEAK evidence: corroboration only. Enough to CLEAR a `true` declaration (half a), never enough
# to CONTRADICT a `false` one (half b) - these tokens appear in briefs the skill forwards and in
# grounding prose, so they say a live instance is somewhere in the picture, not that this skill
# drives it.
INSTANCE_WEAK_TOKENS = (
    "INSTANCE_HANDLE",
    "instance-handle-contract.md",
    "odoo-bin",
    "--test-enable",
)


def _instance_evidence(body: str) -> tuple[list[str], list[str]]:
    """(strong, weak) instance evidence in a SKILL.md body, generated region already removed."""
    strong: list[str] = []
    for m in INSTANCE_LEASE_CALL_RE.finditer(body):
        if NEGATION_RE.search(body[max(0, m.start() - 60):m.start()]):
            continue
        strong.append(f"allocator lease call {m.group(0).strip()!r}")
    for m in INSTANCE_FRONT_DOOR_RE.finditer(body):
        lo = max(0, m.start() - INSTANCE_DISPATCH_WINDOW)
        if not INSTANCE_DISPATCH_VERB_RE.search(body[lo: m.end() + INSTANCE_DISPATCH_WINDOW]):
            continue
        if NEGATION_RE.search(body[lo:m.start()]):
            continue
        line_start = body.rfind("\n", 0, m.start()) + 1
        line_end = body.find("\n", m.end())
        line = body[line_start: line_end if line_end > 0 else len(body)]
        if INSTANCE_ROUTE_AWAY_RE.search(line):
            continue  # hands the instance need to someone else - not a drive
        strong.append(f"dispatches the instance front door: {' '.join(line.split())[:80]!r}")
    weak = [tok for tok in INSTANCE_WEAK_TOKENS if tok in body]
    return strong, weak


def check_instance_truth(findings: list[str], warn_only_findings: list[str]) -> None:
    """16. [instance-truth] - see the module docstring. Half (a) gates --strict; half (b) never
    does, for the reason printed with it."""
    orch = load_orch()
    for name in sorted(orch):
        body = skill_body(name)
        if body is None:
            continue  # coverage gap already reported by rule 1
        body = GENERATED_TOOLS_RE.sub("", body)
        strong, weak = _instance_evidence(body)
        declared = bool(orch[name].get("instance_touching"))

        if declared and not strong and not weak:
            findings.append(
                f"[instance-truth] '{name}' declares instance_touching=true but its SKILL.md shows "
                f"NO instance evidence outside the generated tools block - no allocator lease call, "
                f"no dispatch of odoo-instance/odoo-instance-ops, no odoo-bin, no INSTANCE_HANDLE. "
                f"That declaration derives default_gate_tier=L2, an ALWAYS-human gate no autonomy "
                f"dial can lower, for work the skill never performs. Set it to false (and re-derive "
                f"the tier) or make the skill's instance step explicit in its body."
            )
        if not declared and strong:
            warn_only_findings.append(
                f"[instance-truth] '{name}' declares instance_touching=false but its SKILL.md "
                f"shows it driving one: {'; '.join(strong[:3])}. The field is a FACT, not a tier "
                f"lever - but flipping it today would derive L2 and ADD a human gate the runtime "
                f"sheets deliberately hold at L1 (ephemeral, self-released instances), so this "
                f"half reports and never gates."
            )


def main(argv: list[str]) -> int:
    strict = "--strict" in argv or os.environ.get("ORCH_STRICT") == "1"
    findings: list[str] = []

    orch = load_orch()
    # A skill dir is one that actually ships a SKILL.md; shared-doc dirs (e.g. _shared/) are not skills.
    dirs = {p.name for p in SKILLS_DIR.iterdir() if p.is_dir() and (p / "SKILL.md").exists()} if SKILLS_DIR.exists() else set()

    # 1. Coverage
    for missing in sorted(dirs - set(orch)):
        findings.append(f"[coverage] skill dir '{missing}' has no orchestration entry")
    for extra in sorted(set(orch) - dirs):
        findings.append(f"[coverage] orchestration entry '{extra}' has no skills/ dir")

    # 1c. The shared contract files the per-skill checks reference by substring must actually
    #     exist - otherwise a rename leaves every skill "passing" (stale substring) with a dead
    #     link. Verify the SSOT targets on disk once.
    coding_guidelines_refs = [f"{CODING_GUIDELINES_ROOT}/INDEX.md"]
    coding_guidelines_refs += [f"{CODING_GUIDELINES_ROOT}/{v}/INDEX.md" for v in CODING_GUIDELINES_VERSIONS]
    for rel in (f"snippets/{OSM_SNIPPET}.md", f"snippets/worker-brief.md",
                DESIGN_DOC_PATH, "docs/reference/INSTANCE-LIFECYCLE.md",
                "docs/reference/ODOO-TESTING.md",
                "snippets/context-handoff-protocol.md",
                *coding_guidelines_refs):
        if not (PLUGIN_ROOT / rel).is_file():
            findings.append(f"[ref-target] shared contract file '{rel}' is referenced but missing on disk")

    # 1d. [ref-target] learns the `snippets/references/` path shape (M9): every one of the 13 M9
    # wave-inverted files must have moved its explanation to a sibling `snippets/references/<name>.md`
    # - without this, a rename/typo leaves the sibling orphaned (created under the wrong name) with
    # no mechanical check ever noticing, since [ref-scope] rule (b) forbids any CONSUMER file from
    # naming this path (the read-both hazard), so nothing else on the tree points at it either.
    for rel in INVERTED_SNIPPETS:
        ref_path = REFERENCES_DIR / Path(rel).name
        if not ref_path.is_file():
            findings.append(
                f"[ref-target] '{rel}' is an M9-inverted snippet but its reference sibling "
                f"'{ref_path.relative_to(PLUGIN_ROOT)}' is missing on disk"
            )

    for name in sorted(set(orch) & dirs):
        e = orch[name]
        body = skill_body(name) or ""
        spawn_class = e.get("spawn_class", "")
        stack = e.get("stack", "none")

        # 1b. Enum validity - a typo'd value silently drops the skill from the generated
        #     spawner digest (the planner is then misled), so treat it as a finding.
        if spawn_class not in VALID_SPAWN_CLASS:
            findings.append(f"[enum] '{name}' has invalid spawn_class '{spawn_class}' (not in {sorted(VALID_SPAWN_CLASS)})")
        if stack not in VALID_STACK:
            findings.append(f"[enum] '{name}' has invalid stack '{stack}' (not in {sorted(VALID_STACK)})")

        # 1d. output_mode + default_gate_tier - presence, enum, and gate-tier consistency.
        #     output_mode is authoritative per-skill (read from the Output field); gate_tier
        #     must equal the derivation so the SSOT cannot drift silently.
        output_mode = e.get("output_mode")
        gate_tier = e.get("default_gate_tier")
        if output_mode not in VALID_OUTPUT_MODE:
            findings.append(f"[enum] '{name}' has missing/invalid output_mode '{output_mode}' (not in {sorted(VALID_OUTPUT_MODE)})")
        if gate_tier not in VALID_GATE_TIER:
            findings.append(f"[enum] '{name}' has missing/invalid default_gate_tier '{gate_tier}' (not in {sorted(VALID_GATE_TIER)})")
        if output_mode in VALID_OUTPUT_MODE:
            expected_tier = _derive_gate_tier(spawn_class, bool(e.get("instance_touching")), output_mode, bool(e.get("outward")))
            if gate_tier != expected_tier:
                findings.append(
                    f"[gate-tier] '{name}' default_gate_tier={gate_tier} but derivation says {expected_tier} "
                    f"(spawn_class={spawn_class}, instance_touching={bool(e.get('instance_touching'))}, output_mode={output_mode})"
                )

        # 2. OSM-first contract
        if name in OSM_REQUIRED and OSM_SNIPPET not in body:
            findings.append(f"[osm-first] '{name}' must reference snippets/{OSM_SNIPPET}.md")

        # 3. Design-system fidelity
        if stack in ("frontend", "fullstack") and DESIGN_DOC not in body:
            findings.append(f"[design-system] '{name}' (stack={stack}) must reference {DESIGN_DOC}.md")

        # 4. Instance-touching → CLI grounding
        if e.get("instance_touching") and not any(r in body for r in INSTANCE_REFS):
            findings.append(
                f"[instance] '{name}' is instance_touching but references none of "
                f"{', '.join(INSTANCE_REFS)}"
            )

        # 5. spawn_class vs body - flag only the dangerous drift: a declared `leaf` OR
        #    `orchestrator-nl` that actively dispatches an agent (an orchestrator-nl skill
        #    chains other SKILLS via NL dispatch - Skill tool - and must show no named-AGENT
        #    launch language, same bar as a leaf). (Reverse direction is omitted as noisy; the
        #    orchestration SSOT is authoritative for the spawner declaration.)
        if spawn_class in ("leaf", "orchestrator-nl") and _has_positive_spawn(body):
            findings.append(
                f"[spawn-truth] '{name}' is spawn_class={spawn_class} but body actively dispatches an agent"
            )

        # 6. CHP (Context-Handoff Protocol) - handoff enum + Tier-C fallback documentation.
        #    A skill declaring handoff=send-message or handoff=fork MUST document the Tier-C
        #    fallback (fresh spawn) in its body so the protocol is never a hard dependency.
        handoff = e.get("handoff", "fresh")
        if handoff not in VALID_HANDOFF:
            findings.append(
                f"[enum] '{name}' has invalid handoff '{handoff}' (not in {sorted(VALID_HANDOFF)})"
            )
        if handoff in ("send-message", "fork"):
            body_lower = body.lower()
            has_tier_c_doc = (
                "tier-c" in body_lower
                or "fresh spawn" in body_lower
                or "context-handoff-protocol.md" in body
            )
            if not has_tier_c_doc:
                findings.append(
                    f"[chp-tier-c-fallback] '{name}' declares handoff={handoff!r} but body does not "
                    f"document the Tier-C fallback (fresh spawn). Add a fallback clause or reference "
                    f"snippets/context-handoff-protocol.md."
                )

    # 7. No-hardcode / no-leak across skills + snippets (reference docs exempt: they teach by example)
    scan_files = list(SKILLS_DIR.rglob("SKILL.md")) + list((PLUGIN_ROOT / "snippets").glob("*.md"))
    for f in scan_files:
        text = f.read_text(encoding="utf-8")
        rel = f.relative_to(PLUGIN_ROOT)
        if SELF_REF_RE.search(text):
            findings.append(f"[no-hardcode] self-referential CSS custom property in {rel}")
        if _machine_path_leak(text):
            findings.append(f"[no-leak] machine-specific absolute path in {rel}")
        for _lang, block in FENCE_RE.findall(text):
            if HEX_RE.search(block):
                findings.append(f"[no-hardcode] hardcoded hex color in a style code fence in {rel}")
                break

    # 8. Agent role (see check_agent_roles docstring - LIVE: roles are populated for every agent)
    check_agent_roles(findings)

    # 11. [role-scope] - LIVE and enforcing (part of `findings`, gates --strict like rules 1-8).
    check_role_scope(findings)

    # 13, 14b, 15. [card-budget] / [ref-scope] half (b) / [no-provenance] (M9/M10,
    # 12-design-final.md) - LIVE and enforcing, part of `findings` like rules 1-8 and 11.
    check_card_budget(findings)
    check_ref_scope_no_reference_pointer(findings)
    check_no_provenance(findings)

    # 16. [instance-truth] - half (a) joins `findings` (gates --strict); half (b) is collected into
    # its OWN list below so its print message can state why it cannot gate yet.
    instance_truth_warn_only_findings: list[str] = []
    check_instance_truth(findings, instance_truth_warn_only_findings)

    # 9/10. [wait-scope] / [wait-mechanism] (M1 guard) - WARN-FIRST for one release: collected
    # into their OWN list, never gating the strict exit below, no matter how many fire (see the
    # module-level note above check_wait_scope/check_wait_mechanism for why and the flip plan).
    warn_only_findings: list[str] = []
    check_wait_scope(warn_only_findings)
    check_wait_mechanism(warn_only_findings)

    # 14a. [ref-scope] half (a) (M9) - WARN-FIRST for one release, SEPARATE list from 9/10 so the
    # print label stays accurate (see check_ref_scope_citation_anchor's own docstring).
    ref_scope_warn_only_findings: list[str] = []
    check_ref_scope_citation_anchor(ref_scope_warn_only_findings)

    # 12. [brief-fields] - WARN-ONLY, PERMANENTLY (never scheduled to flip to strict - contrast
    # rules 9-10 above). Collected into its OWN list so the print message does not claim a
    # migration window that does not apply to it.
    permanent_warn_only_findings: list[str] = []
    check_brief_fields(permanent_warn_only_findings)

    if findings:
        print(f"check_orchestration: {len(findings)} finding(s)"
              f" ({'STRICT' if strict else 'warn-only'}):")
        for fnd in findings:
            print(f"  - {fnd}")
        if not strict:
            print("  (warn-only mode - exit 0; pass --strict to enforce)")

    if warn_only_findings:
        print(f"check_orchestration: {len(warn_only_findings)} warn-only finding(s) "
              f"([wait-scope]/[wait-mechanism], ships warn-first for one release - "
              f"NEVER gates --strict):")
        for fnd in warn_only_findings:
            print(f"  - {fnd}")

    if ref_scope_warn_only_findings:
        print(f"check_orchestration: {len(ref_scope_warn_only_findings)} warn-only finding(s) "
              f"([ref-scope] half (a), citation-anchor, ships warn-first for one release - "
              f"NEVER gates --strict):")
        for fnd in ref_scope_warn_only_findings:
            print(f"  - {fnd}")

    if permanent_warn_only_findings:
        print(f"check_orchestration: {len(permanent_warn_only_findings)} warn-only finding(s) "
              f"([brief-fields], warn-only PERMANENTLY by design - NEVER gates --strict, no "
              f"migration window):")
        for fnd in permanent_warn_only_findings:
            print(f"  - {fnd}")

    if instance_truth_warn_only_findings:
        print(f"check_orchestration: {len(instance_truth_warn_only_findings)} warn-only finding(s) "
              f"([instance-truth] half (b), under-declaration - NEVER gates --strict while "
              f"_derive_gate_tier still maps any instance_touching=true to L2; correcting these "
              f"rows today would ADD human gates the runtime sheets hold at L1):")
        for fnd in instance_truth_warn_only_findings:
            print(f"  - {fnd}")

    if findings and strict:
        return 1

    if (not findings and not warn_only_findings and not ref_scope_warn_only_findings
            and not permanent_warn_only_findings and not instance_truth_warn_only_findings):
        print("check_orchestration: OK - all orchestration contracts satisfied.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
