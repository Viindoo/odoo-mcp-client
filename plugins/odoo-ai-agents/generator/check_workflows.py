#!/usr/bin/env python3
"""CI workflow validator: assert every workflows/*.workflow.yaml conforms to the schema.

Schema SSOT: plugins/odoo-ai-agents/workflows/_schema.md
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

ROOT = pathlib.Path(__file__).resolve().parent.parent  # plugins/odoo-ai-agents
WORKFLOWS_DIR = ROOT / "workflows"
SKILLS_DIR = ROOT / "skills"
COMMANDS_DIR = ROOT / "commands"

# A command for a driver-required (on_complete) workflow MUST carry this machine-readable sentinel to
# declare it engages the run-driver (via intake Phase P / a 1-node run) instead of a bare
# workflow-chaining dispatch. Its presence clears the driver-required warning for that command.
RUN_DRIVER_SENTINEL = "engages-run-driver"

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

# Gate tiers for cross-workflow on_complete transitions (mirror the run-driver / registry
# default_gate_tier vocabulary). L2 = irreversible/outward → always human.
ALLOWED_GATE_TIERS = {"L0", "L1", "L2"}

REQUIRED_TOP_LEVEL = ["name", "domain", "team_pattern", "description", "output_dir", "phases"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _skill_exists(skill_name: str) -> bool:
    return (SKILLS_DIR / skill_name).is_dir()


def _workflow_names() -> set[str]:
    """All declared workflow names (from each *.workflow.yaml `name:` field, plus file stem)."""
    names: set[str] = set()
    if not WORKFLOWS_DIR.is_dir():
        return names
    for wf in WORKFLOWS_DIR.glob("*.workflow.yaml"):
        names.add(wf.name[: -len(".workflow.yaml")])
        try:
            d = yaml.safe_load(wf.read_text(encoding="utf-8")) or {}
            if isinstance(d, dict) and d.get("name"):
                names.add(str(d["name"]))
        except Exception:
            pass
    return names


def _validate_on_complete(data: dict, self_name: str, fname: str) -> list[str]:
    """Validate the optional top-level `on_complete` cross-workflow transition list.

    Each entry must: have a string `when` + `reason`; a `next` that resolves to an existing
    skill OR workflow (and never self-loops back to this same workflow); and a `gate_tier` in
    the allowed set. on_complete only EMITs a next[] for run-driver - it never self-dispatches."""
    errors: list[str] = []
    oc = data.get("on_complete")
    if oc is None:
        return errors
    if not isinstance(oc, list):
        errors.append(f"File '{fname}': 'on_complete' must be a list")
        return errors
    wf_names = _workflow_names()
    for i, entry in enumerate(oc):
        p = f"File '{fname}': on_complete[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{p} must be a mapping")
            continue
        if not isinstance(entry.get("when"), str) or not entry.get("when"):
            errors.append(f"{p}: 'when' is required and must be a non-empty string")
        if not isinstance(entry.get("reason"), str) or not entry.get("reason"):
            errors.append(f"{p}: 'reason' is required and must be a non-empty string")
        nxt = entry.get("next")
        if not isinstance(nxt, str) or not nxt:
            errors.append(f"{p}: 'next' is required and must be a non-empty string")
        else:
            if nxt == self_name:
                errors.append(f"{p}: 'next' must not point back to this same workflow (self-loop)")
            elif not (_skill_exists(nxt) or nxt in wf_names):
                errors.append(f"{p}: 'next' = '{nxt}' is neither an existing skill nor a known workflow")
        tier = entry.get("gate_tier")
        if tier is not None and tier not in ALLOWED_GATE_TIERS:
            errors.append(f"{p}: gate_tier '{tier}' not in {sorted(ALLOWED_GATE_TIERS)}")
    return errors


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

    # Required top-level fields - empty/whitespace strings count as missing
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

    # domain enum - empty/whitespace is already caught by required-field check above;
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

    # optional cross-workflow transition block
    errors.extend(_validate_on_complete(data, name or stem, path.name))

    return errors


# ---------------------------------------------------------------------------
# Driver-required warning (Flag 2): a workflow declaring on_complete is "driver-required" -
# its emitted next[] is only auto-dispatched when run under a run-driver (intake Phase P).
# A slash command that dispatches such a workflow DIRECTLY (bypassing intake) makes on_complete
# degrade to a human suggestion. Surface that as a WARNING (non-fatal) so a future command does
# not silently break the cross-workflow chain.
#
# Clearing mechanism: if a command carries the RUN_DRIVER_SENTINEL comment, it explicitly
# declares that it engages the run-driver (via /odoo-intake Phase P or a 1-node run). The
# sentinel suppresses the warning for that command. Commands that reference the workflow name
# but lack the sentinel still trigger the warning - so adding the sentinel is meaningful
# (it documents intent AND gates the check) while omitting it still gets caught.
# ---------------------------------------------------------------------------


def _driver_required_warnings() -> list[str]:
    warnings: list[str] = []
    if not (WORKFLOWS_DIR.is_dir() and COMMANDS_DIR.is_dir()):
        return warnings
    # workflows that declare on_complete → set of {file stem, declared name}
    driver_required: dict[str, set[str]] = {}
    for wf in WORKFLOWS_DIR.glob("*.workflow.yaml"):
        try:
            d = yaml.safe_load(wf.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if isinstance(d, dict) and d.get("on_complete"):
            stem = wf.name[: -len(".workflow.yaml")]
            names = {stem}
            if d.get("name"):
                names.add(str(d["name"]))
            driver_required[stem] = names
    if not driver_required:
        return warnings
    for cmd in COMMANDS_DIR.glob("*.md"):
        text = cmd.read_text(encoding="utf-8")
        if RUN_DRIVER_SENTINEL in text:
            continue  # command explicitly declares it engages the run-driver
        for stem, names in driver_required.items():
            if any(n in text for n in names):
                warnings.append(
                    f"command '{cmd.name}' references driver-required workflow '{stem}' "
                    f"(it declares on_complete). Ensure the command engages the run-driver "
                    f"(intake Phase P / a 1-node run), not a direct workflow-chaining dispatch - "
                    f"otherwise on_complete degrades to a human suggestion."
                )
    return warnings


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

    warnings = _driver_required_warnings()
    for w in warnings:
        print(f"WARN: {w}", file=sys.stderr)

    print(f"OK: {len(workflow_files)} workflow(s) valid"
          + (f" ({len(warnings)} warning(s))." if warnings else "."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
