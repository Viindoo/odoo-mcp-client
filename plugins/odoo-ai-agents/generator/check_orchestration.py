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

WARN-FIRST: by default this prints findings and exits 0 (migration-friendly). Pass --strict
(or set ORCH_STRICT=1) to exit 1 on any finding - flip that on once all skills comply.

Run from the repo root or anywhere; paths are resolved relative to this file.
"""

import json
import os
import re
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent.resolve()
DEPS_FILE = Path(__file__).parent / "skill_tool_deps.json"
SKILLS_DIR = PLUGIN_ROOT / "skills"
AGENTS_DIR = PLUGIN_ROOT / "agents"

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
# Context-Handoff Protocol (CHP) tier declared per skill. send-message = Tier-A (lead resumes
# a named worker via SendMessage); fork = Tier-B (subagent_type=fork fan-out); fresh = Tier-C
# default (cold-spawn every turn - always correct baseline). Absence == fresh.
VALID_HANDOFF = {"send-message", "fork", "fresh"}


def _derive_gate_tier(spawn_class: str, instance_touching: bool, output_mode: str,
                      outward: bool = False) -> str:
    """Derive the registry default_gate_tier for a SKILL. L2 = irreversible/outward → ALWAYS
    human gate (the dial can never lower it). L1 = writes internal files. L0 = read-only/chat.

    NOTE - there is no `spawner-wave` branch anymore. run-harness's OWN between-wave integration
    advance is L1 (autonomous drive-to-done: its instance touches are EPHEMERAL test DBs; each wave
    auto-advances on a GREEN cumulative close-gate with NO per-wave PR, and the only irreversible
    landing is the DOWNSTREAM outward merge - odoo-pr-monitoring's merge-to-principal - of the single
    run-level PR the terminal integrate land-tail opens once after the final wave). That L1 is a
    run-harness NODE tier applied by the driver (see run-harness SKILL.md § Gate-tier resolution +
    workflow-harness.md §8.4), NOT a value derived from any skill's registry fields, so it is not
    computed here. A DYNAMIC (unplanned) node (including a wave) stays L2 via run-harness's
    all-dynamic-L2 rule. `outward` is checked first so an outward skill always derives L2."""
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

    if findings:
        print(f"check_orchestration: {len(findings)} finding(s)"
              f" ({'STRICT' if strict else 'warn-only'}):")
        for fnd in findings:
            print(f"  - {fnd}")
        if strict:
            return 1
        print("  (warn-only mode - exit 0; pass --strict to enforce)")
        return 0

    print("check_orchestration: OK - all orchestration contracts satisfied.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
