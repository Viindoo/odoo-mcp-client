#!/usr/bin/env python3
"""CI workflow validator: assert every workflows/*.workflow.yaml conforms to the schema.

Schema SSOT: plugins/odoo-semantic-skills/workflows/_schema.md
Rules enforced:
  1. All required top-level fields present (name, domain, team_pattern, description,
     output_dir, phases).
  2. `domain` in the 9 allowed persona buckets.
  3. `team_pattern` in the 6 allowed pattern values.
  4. `output_dir` starts with '.odoo-ai/'.
  5. Each phase has exactly one of: skill, inline (true), agent.
  6. For phases with `skill`: the skill directory exists under plugins/.../skills/.
  7. `model_tier` in {haiku, sonnet, opus, inherit}.
  8. `name` matches the file stem.
  9. `description` does not end with '.', '!', or '?'.
 10. Phases with `skill` or `agent` (not inline) must have a non-empty `nl_trigger`.
"""
import sys
import pathlib

try:
    import yaml
except ImportError:
    print(
        "ERROR: PyYAML not installed. Run: pip install pyyaml",
        file=sys.stderr,
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = pathlib.Path(__file__).resolve().parent.parent  # plugins/odoo-semantic-skills
WORKFLOWS_DIR = ROOT / "workflows"
SKILLS_DIR = ROOT / "skills"

# ---------------------------------------------------------------------------
# Allowed enum values
# ---------------------------------------------------------------------------

ALLOWED_DOMAINS = {
    "engineering",
    "sales",
    "presales",
    "marketing",
    "strategy",
    "qa",
    "support",
    "content",
    "consultant",
}

ALLOWED_PATTERNS = {
    "Pipeline",
    "Fan-out",
    "Expert-Pool",
    "Producer-Reviewer",
    "Supervisor",
    "Hierarchical",
}

ALLOWED_MODEL_TIERS = {"haiku", "sonnet", "opus", "inherit"}

REQUIRED_TOP_LEVEL = ["name", "domain", "team_pattern", "description", "output_dir", "phases"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _skill_exists(skill_name: str) -> bool:
    return (SKILLS_DIR / skill_name).is_dir()


def _validate_phase(phase: dict, phase_idx: int, workflow_name: str) -> list[str]:
    errors = []
    prefix = f"Workflow '{workflow_name}' phase[{phase_idx}]"

    phase_id = phase.get("id", f"<index {phase_idx}>")
    prefix_id = f"Workflow '{workflow_name}' phase '{phase_id}'"

    # Exactly one of skill / inline / agent
    has_skill = bool(phase.get("skill"))
    has_inline = phase.get("inline") is True
    has_agent = bool(phase.get("agent"))
    presence = sum([has_skill, has_inline, has_agent])
    if presence == 0:
        errors.append(
            f"{prefix_id}: must have exactly one of 'skill', 'inline: true', or 'agent'"
        )
    elif presence > 1:
        errors.append(
            f"{prefix_id}: only one of 'skill', 'inline: true', 'agent' is allowed per phase"
        )

    # skill must exist
    if has_skill:
        skill_name = phase["skill"]
        if not _skill_exists(skill_name):
            errors.append(
                f"{prefix_id}: skill '{skill_name}' not found in skills/ directory"
            )

    # nl_trigger required for skill/agent phases (not inline)
    if (has_skill or has_agent) and not has_inline:
        nl_trigger = phase.get("nl_trigger", "")
        if not (isinstance(nl_trigger, str) and nl_trigger.strip()):
            errors.append(
                f"{prefix_id}: 'nl_trigger' is required and must be non-empty "
                f"for phases with 'skill' or 'agent'"
            )

    # model_tier enum
    tier = phase.get("model_tier")
    if tier is None:
        errors.append(f"{prefix_id}: missing required 'model_tier'")
    elif tier not in ALLOWED_MODEL_TIERS:
        errors.append(
            f"{prefix_id}: model_tier '{tier}' not in {sorted(ALLOWED_MODEL_TIERS)}"
        )

    return errors


def _workflow_stem(path: pathlib.Path) -> str:
    """Return the workflow name stem, stripping the double extension .workflow.yaml."""
    name = path.name
    if name.endswith(".workflow.yaml"):
        return name[: -len(".workflow.yaml")]
    return path.stem


def _validate_workflow(path: pathlib.Path) -> list[str]:
    errors = []
    stem = _workflow_stem(path)  # filename without .workflow.yaml

    try:
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        return [f"File '{path.name}': YAML parse error: {exc}"]

    if not isinstance(data, dict):
        return [f"File '{path.name}': top-level must be a YAML mapping, got {type(data).__name__}"]

    # Required top-level fields — empty/whitespace strings count as missing
    for field in REQUIRED_TOP_LEVEL:
        value = data.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append(f"File '{path.name}': missing required field '{field}'")

    # name matches stem
    name = data.get("name", "")
    if name and name != stem:
        errors.append(
            f"File '{path.name}': 'name' field '{name}' does not match file stem '{stem}'"
        )

    # domain enum — empty/whitespace is already caught by required-field check above;
    # skip enum check only when the field is truly absent (avoids duplicate error).
    domain = data.get("domain", "")
    if domain is not None and domain not in ALLOWED_DOMAINS:
        errors.append(
            f"File '{path.name}': domain '{domain}' not in allowed values {sorted(ALLOWED_DOMAINS)}"
        )

    # team_pattern enum
    pattern = data.get("team_pattern", "")
    if pattern is not None and pattern not in ALLOWED_PATTERNS:
        errors.append(
            f"File '{path.name}': team_pattern '{pattern}' not in allowed values "
            f"{sorted(ALLOWED_PATTERNS)}"
        )

    # output_dir must start with .odoo-ai/
    output_dir = data.get("output_dir", "")
    if output_dir and not str(output_dir).startswith(".odoo-ai/"):
        errors.append(
            f"File '{path.name}': output_dir '{output_dir}' must start with '.odoo-ai/'"
        )

    # description trailing punctuation
    desc = data.get("description", "")
    if isinstance(desc, str):
        desc_stripped = desc.strip()
        if desc_stripped and desc_stripped[-1] in ".!?":
            errors.append(
                f"File '{path.name}': description must not end with '.', '!', or '?' "
                f"(found: ...{desc_stripped[-40:]!r})"
            )

    # phases
    phases = data.get("phases")
    if isinstance(phases, list):
        if len(phases) == 0:
            errors.append(f"File '{path.name}': 'phases' must have at least 1 entry")
        for idx, phase in enumerate(phases):
            if not isinstance(phase, dict):
                errors.append(
                    f"File '{path.name}': phases[{idx}] must be a mapping, "
                    f"got {type(phase).__name__}"
                )
                continue
            errors.extend(_validate_phase(phase, idx, name or stem))
    elif phases is not None:
        errors.append(f"File '{path.name}': 'phases' must be a list")

    return errors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    workflow_files = sorted(
        f for f in WORKFLOWS_DIR.glob("*.workflow.yaml") if f.is_file()
    )

    if not workflow_files:
        print("OK: 0 workflows found (nothing to validate).")
        return 0

    all_errors: list[str] = []
    for wf_path in workflow_files:
        all_errors.extend(_validate_workflow(wf_path))

    if all_errors:
        for err in all_errors:
            print(f"ERROR: {err}", file=sys.stderr)
        print(
            f"\nFAIL: {len(all_errors)} error(s) across {len(workflow_files)} workflow(s).",
            file=sys.stderr,
        )
        return 1

    print(f"OK: {len(workflow_files)} workflow(s) valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
