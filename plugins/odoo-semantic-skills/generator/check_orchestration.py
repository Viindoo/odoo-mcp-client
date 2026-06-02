#!/usr/bin/env python3
"""
check_orchestration.py — lint the Declarative Capability & Contract Layer.

Validates that orchestration metadata (generator/skill_tool_deps.json -> "orchestration")
is complete and that skills thread the shared contracts they are required to:

  1. Coverage     — every skills/<dir> has an orchestration entry, and vice versa.
  2. OSM-first    — skills that spawn/fan-out workers writing Odoo (wave, workflow-runner,
                    odoo-brl) reference snippets/osm-first-contract.md.
  3. Design-sys   — skills with stack in {frontend, fullstack} reference
                    docs/reference/odoo-design-system-fidelity.md.
  4. Instance     — skills with instance_touching=true reference cli_help / the lifecycle
                    docs (so they ground the CLI per target version instead of assuming).
  5. Spawn truth  — spawn_class is consistent with the SKILL.md body (a 'leaf' must not show
                    Agent-tool spawn language; a 'spawner-*' should).
  6. No hardcode / no leak — self-referential CSS custom properties, machine-specific
                    absolute paths, and hardcoded hex inside skill SCSS code fences.

WARN-FIRST: by default this prints findings and exits 0 (migration-friendly). Pass --strict
(or set OSS_LINT_STRICT=1) to exit 1 on any finding — flip that on once all skills comply.

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

OSM_SNIPPET = "osm-first-contract"
DESIGN_DOC = "odoo-design-system-fidelity"
INSTANCE_REFS = ("cli_help", "INSTANCE-LIFECYCLE", "ODOO-TESTING")

# Skills that fan-out / spawn workers which may write Odoo code → must carry OSM-first.
OSM_REQUIRED = {"wave", "workflow-runner", "odoo-brl"}

# High-precision ACTIVE dispatch signals in a SKILL.md body. Deliberately narrow: a generic
# "spawn subagents" phrase is NOT included because it appears in negated capability statements
# ("this skill does not invoke other skills or spawn subagents") and is pure noise. We only
# flag the dangerous drift — a skill declared `leaf` that actively dispatches an agent. The
# orchestration SSOT (skill_tool_deps.json) is the authoritative classification.
SPAWN_BODY_RE = re.compile(
    r"(invoke the Agent tool|call the Agent tool|dispatch(?:es)? (?:to )?the [a-z][a-z-]+ agent)",
    re.I,
)
NEGATION_RE = re.compile(r"\b(not|never|cannot|non-|n't|may not)\b", re.I)


def _has_positive_spawn(body: str) -> bool:
    """True if the body shows a real (non-negated) active agent-dispatch instruction."""
    for m in SPAWN_BODY_RE.finditer(body):
        preceding = body[max(0, m.start() - 45):m.start()]
        if NEGATION_RE.search(preceding):
            continue  # e.g. "do NOT invoke the Agent tool" / "does not dispatch the X agent"
        return True
    return False
SELF_REF_RE = re.compile(r"--([a-z0-9-]+)\s*:\s*var\(\s*--\1\b", re.I)
MACHINE_PATH_RE = re.compile(r"/(?:home|Users)/([A-Za-z0-9._-]+)/")
# Placeholder usernames are documentation, not a leak of this machine's real home.
PLACEHOLDER_USERS = {"user", "username", "you", "youruser", "your-user", "me", "name", "odoo"}


def _machine_path_leak(text: str) -> bool:
    """True if text contains a real (non-placeholder) absolute home path — a machine leak."""
    return any(u.lower() not in PLACEHOLDER_USERS for u in MACHINE_PATH_RE.findall(text))
HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b")
FENCE_RE = re.compile(r"```(scss|css|sass|less)\b(.*?)```", re.S)


def load_orch():
    data = json.loads(DEPS_FILE.read_text(encoding="utf-8"))
    return {k: v for k, v in data.get("orchestration", {}).items() if not k.startswith("_")}


def skill_body(name: str) -> str | None:
    p = SKILLS_DIR / name / "SKILL.md"
    return p.read_text(encoding="utf-8") if p.exists() else None


def main(argv: list[str]) -> int:
    strict = "--strict" in argv or os.environ.get("OSS_LINT_STRICT") == "1"
    findings: list[str] = []

    orch = load_orch()
    dirs = {p.name for p in SKILLS_DIR.iterdir() if p.is_dir()} if SKILLS_DIR.exists() else set()

    # 1. Coverage
    for missing in sorted(dirs - set(orch)):
        findings.append(f"[coverage] skill dir '{missing}' has no orchestration entry")
    for extra in sorted(set(orch) - dirs):
        findings.append(f"[coverage] orchestration entry '{extra}' has no skills/ dir")

    for name in sorted(set(orch) & dirs):
        e = orch[name]
        body = skill_body(name) or ""
        spawn_class = e.get("spawn_class", "")
        stack = e.get("stack", "none")

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

        # 5. spawn_class vs body — flag only the dangerous drift: a declared `leaf` that
        #    actively dispatches an agent. (Reverse direction is omitted as noisy; the
        #    orchestration SSOT is authoritative for the spawner declaration.)
        if spawn_class == "leaf" and _has_positive_spawn(body):
            findings.append(
                f"[spawn-truth] '{name}' is spawn_class=leaf but body actively dispatches an agent"
            )

    # 6. No-hardcode / no-leak across skills + snippets (reference docs exempt: they teach by example)
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

    if findings:
        print(f"check_orchestration: {len(findings)} finding(s)"
              f" ({'STRICT' if strict else 'warn-only'}):")
        for fnd in findings:
            print(f"  - {fnd}")
        if strict:
            return 1
        print("  (warn-only mode — exit 0; pass --strict to enforce)")
        return 0

    print("check_orchestration: OK — all orchestration contracts satisfied.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
