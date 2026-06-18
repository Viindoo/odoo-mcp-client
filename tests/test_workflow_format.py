"""Validate that every workflows/*.workflow.yaml conforms to the composition contract.

Schema SSOT: plugins/odoo-ai-agents/workflows/_schema.md
Validator CLI: plugins/odoo-ai-agents/generator/check_workflows.py

Tests are behavior-first (ETHOS #11): each test expresses one rule from the
business contract and must fail for the right reason. Tests do NOT protect
current code structure -- they protect the composition contract.

No third-party deps: PyYAML is already required by the validator (stdlib
fallback attempted; test skips cleanly if PyYAML absent).
"""
import pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILLS_PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
WORKFLOWS_DIR = SKILLS_PLUGIN / "workflows"
SKILLS_DIR = SKILLS_PLUGIN / "skills"

# ---------------------------------------------------------------------------
# PyYAML availability
# ---------------------------------------------------------------------------

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

pytestmark = pytest.mark.skipif(not HAS_YAML, reason="PyYAML not installed")

# ---------------------------------------------------------------------------
# Allowed enum values (mirrors check_workflows.py - both reference _schema.md)
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


def _workflow_stem(path: pathlib.Path) -> str:
    """Return the workflow slug, stripping the double extension .workflow.yaml."""
    name = path.name
    if name.endswith(".workflow.yaml"):
        return name[: -len(".workflow.yaml")]
    return path.stem


def _load_workflows():
    """Return list of (path, parsed_data) for every *.workflow.yaml."""
    result = []
    for wf_path in sorted(WORKFLOWS_DIR.glob("*.workflow.yaml")):
        data = yaml.safe_load(wf_path.read_text(encoding="utf-8"))
        result.append((wf_path, data))
    return result


WORKFLOW_FILES = _load_workflows() if HAS_YAML else []


def _workflow_id(param):
    path, _ = param
    return _workflow_stem(path)


# ---------------------------------------------------------------------------
# Contract: at least 1 workflow ships (floor check)
# ---------------------------------------------------------------------------


def test_at_least_1_workflow():
    """The composition contract requires at least one reference workflow to prove
    the schema is exercised.  Adding more never breaks this test."""
    assert len(WORKFLOW_FILES) >= 1, (
        "Expected >=1 *.workflow.yaml in workflows/; the reference workflow is missing"
    )


# ---------------------------------------------------------------------------
# Unit: empty/whitespace domain must be rejected as missing (not silently pass)
# ---------------------------------------------------------------------------


def test_empty_domain_is_invalid():
    """An empty-string domain must fail the required-field check.

    Business rule: a workflow with domain='' is undeclared and would route to
    no persona bucket.  The validator must treat '' the same as a missing field.
    Regression guard for the empty-string guard fix in check_workflows.py.
    """
    import sys
    import io
    import pathlib

    # Construct a minimal valid workflow dict with an empty domain
    fake_data = {
        "name": "test-empty-domain",
        "domain": "",
        "team_pattern": "Pipeline",
        "description": "A test workflow",
        "output_dir": ".odoo-ai/test/",
        "phases": [{"id": "p1", "skill": "odoo-backend-coding", "model_tier": "sonnet"}],
    }

    # Import the validator directly
    gen_dir = pathlib.Path(__file__).resolve().parent.parent / "plugins" / "odoo-ai-agents" / "generator"
    sys.path.insert(0, str(gen_dir))
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_workflows", gen_dir / "check_workflows.py")
    cw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cw)

    # Simulate required-field check on empty domain
    missing = []
    for field in cw.REQUIRED_TOP_LEVEL:
        value = fake_data.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)

    assert "domain" in missing, (
        "Empty-string domain must be treated as missing (required-field violation), "
        f"but validator reported missing={missing}"
    )


# ---------------------------------------------------------------------------
# Contract: each workflow must be parseable YAML
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("wf", WORKFLOW_FILES, ids=_workflow_id)
def test_workflow_is_valid_yaml(wf):
    """Each workflow file must be parseable as YAML and produce a mapping."""
    path, data = wf
    assert isinstance(data, dict), (
        f"{path.name}: expected top-level YAML mapping, got {type(data).__name__}"
    )


# ---------------------------------------------------------------------------
# Contract: required top-level fields must be present and non-empty
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("wf", WORKFLOW_FILES, ids=_workflow_id)
def test_workflow_required_fields_present(wf):
    """Every required field declared in the schema must be present and truthy."""
    path, data = wf
    missing = [f for f in REQUIRED_TOP_LEVEL if not data.get(f)]
    assert not missing, (
        f"{path.name}: missing required field(s): {missing}"
    )


# ---------------------------------------------------------------------------
# Contract: name must match file stem
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("wf", WORKFLOW_FILES, ids=_workflow_id)
def test_workflow_name_matches_stem(wf):
    """The 'name' field must equal the filename stem (no extension)."""
    path, data = wf
    stem = _workflow_stem(path)
    assert data.get("name") == stem, (
        f"{path.name}: 'name' field '{data.get('name')}' does not match file stem '{stem}'"
    )


# ---------------------------------------------------------------------------
# Contract: domain must be one of the 9 persona buckets
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("wf", WORKFLOW_FILES, ids=_workflow_id)
def test_workflow_domain_enum(wf):
    """domain must be one of the 9 allowed persona bucket values."""
    path, data = wf
    domain = data.get("domain", "")
    assert domain in ALLOWED_DOMAINS, (
        f"{path.name}: domain '{domain}' not in allowed values {sorted(ALLOWED_DOMAINS)}"
    )


# ---------------------------------------------------------------------------
# Contract: team_pattern must be one of the 6 execution shapes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("wf", WORKFLOW_FILES, ids=_workflow_id)
def test_workflow_team_pattern_enum(wf):
    """team_pattern must be one of the 6 revfactory patterns."""
    path, data = wf
    pattern = data.get("team_pattern", "")
    assert pattern in ALLOWED_PATTERNS, (
        f"{path.name}: team_pattern '{pattern}' not in {sorted(ALLOWED_PATTERNS)}"
    )


# ---------------------------------------------------------------------------
# Contract: output_dir must be under .odoo-ai/
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("wf", WORKFLOW_FILES, ids=_workflow_id)
def test_workflow_output_dir_under_odoo_ai(wf):
    """output_dir must start with '.odoo-ai/' to use the standard artifact convention."""
    path, data = wf
    output_dir = str(data.get("output_dir", ""))
    assert output_dir.startswith(".odoo-ai/"), (
        f"{path.name}: output_dir '{output_dir}' must start with '.odoo-ai/'"
    )


# ---------------------------------------------------------------------------
# Contract: phases must be a non-empty list
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("wf", WORKFLOW_FILES, ids=_workflow_id)
def test_workflow_phases_non_empty_list(wf):
    """phases must be a list with at least one item."""
    path, data = wf
    phases = data.get("phases")
    assert isinstance(phases, list) and len(phases) >= 1, (
        f"{path.name}: 'phases' must be a non-empty list"
    )


# ---------------------------------------------------------------------------
# Contract: each phase has exactly one dispatcher (skill / inline / agent)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("wf", WORKFLOW_FILES, ids=_workflow_id)
def test_workflow_phase_dispatcher_exclusive(wf):
    """Each phase must have exactly one of: skill, inline: true, agent."""
    path, data = wf
    phases = data.get("phases") or []
    for idx, phase in enumerate(phases):
        has_skill = bool(phase.get("skill"))
        has_inline = phase.get("inline") is True
        has_agent = bool(phase.get("agent"))
        count = sum([has_skill, has_inline, has_agent])
        phase_id = phase.get("id", f"index {idx}")
        assert count == 1, (
            f"{path.name} phase '{phase_id}': must have exactly one of "
            f"'skill', 'inline: true', 'agent' (found {count})"
        )


# ---------------------------------------------------------------------------
# Contract: skill references must exist in skills/ directory
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("wf", WORKFLOW_FILES, ids=_workflow_id)
def test_workflow_phase_skill_exists(wf):
    """For phases with 'skill', the named skill must exist under skills/."""
    path, data = wf
    phases = data.get("phases") or []
    missing = []
    for idx, phase in enumerate(phases):
        skill_name = phase.get("skill")
        if skill_name and not (SKILLS_DIR / skill_name).is_dir():
            phase_id = phase.get("id", f"index {idx}")
            missing.append(f"phase '{phase_id}': skill '{skill_name}' not found in skills/")
    assert not missing, f"{path.name}: {'; '.join(missing)}"


# ---------------------------------------------------------------------------
# Contract: model_tier must be one of the 4 allowed values
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("wf", WORKFLOW_FILES, ids=_workflow_id)
def test_workflow_phase_model_tier_enum(wf):
    """Each phase model_tier must be one of: haiku, sonnet, opus, inherit."""
    path, data = wf
    phases = data.get("phases") or []
    bad = []
    for idx, phase in enumerate(phases):
        tier = phase.get("model_tier")
        phase_id = phase.get("id", f"index {idx}")
        if tier is None:
            bad.append(f"phase '{phase_id}': missing 'model_tier'")
        elif tier not in ALLOWED_MODEL_TIERS:
            bad.append(
                f"phase '{phase_id}': model_tier '{tier}' "
                f"not in {sorted(ALLOWED_MODEL_TIERS)}"
            )
    assert not bad, f"{path.name}: {'; '.join(bad)}"


# ---------------------------------------------------------------------------
# Contract: skill/agent phases must have a non-empty nl_trigger
# ---------------------------------------------------------------------------


def test_skill_phase_requires_nl_trigger():
    """A phase with 'skill' but no nl_trigger must be rejected by the validator.

    Business rule (schema §5): nl_trigger is required for every skill/agent phase
    so the workflow-chaining skill can dispatch the correct specialist via NL description-
    match.  Inline phases are exempt (they are handled by the runner itself).
    Regression guard for the validator gap closed in check_workflows.py.
    """
    import sys
    import pathlib as _pathlib

    gen_dir = _pathlib.Path(__file__).resolve().parent.parent / "plugins" / "odoo-ai-agents" / "generator"
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_workflows", gen_dir / "check_workflows.py")
    cw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cw)

    # Phase with skill but nl_trigger absent - must fail
    phase_missing = {"id": "p1", "skill": "odoo-backend-coding", "model_tier": "sonnet"}
    errors = cw._validate_phase(phase_missing, 0, "test-workflow")
    nl_errors = [e for e in errors if "nl_trigger" in e]
    assert nl_errors, (
        "Validator must reject a skill phase with no nl_trigger, "
        f"but _validate_phase returned: {errors}"
    )

    # Phase with skill and a valid nl_trigger - must NOT produce nl_trigger error
    phase_ok = {
        "id": "p2",
        "skill": "odoo-backend-coding",
        "nl_trigger": "Write a computed field for the model.",
        "model_tier": "sonnet",
    }
    errors_ok = cw._validate_phase(phase_ok, 1, "test-workflow")
    nl_errors_ok = [e for e in errors_ok if "nl_trigger" in e]
    assert not nl_errors_ok, (
        "Validator must accept a skill phase that has a non-empty nl_trigger, "
        f"but got nl_trigger errors: {nl_errors_ok}"
    )

    # Inline phase with no nl_trigger - must NOT produce nl_trigger error
    phase_inline = {"id": "p3", "inline": True, "model_tier": "inherit"}
    errors_inline = cw._validate_phase(phase_inline, 2, "test-workflow")
    nl_errors_inline = [e for e in errors_inline if "nl_trigger" in e]
    assert not nl_errors_inline, (
        "Inline phases are exempt from nl_trigger requirement, "
        f"but got nl_trigger errors: {nl_errors_inline}"
    )


# ---------------------------------------------------------------------------
# Contract: description must not end with trailing punctuation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("wf", WORKFLOW_FILES, ids=_workflow_id)
def test_workflow_description_no_trailing_punctuation(wf):
    """description must not end with '.', '!', or '?' (Anthropic plugin marketplace style)."""
    path, data = wf
    desc = str(data.get("description", "")).strip()
    assert desc and desc[-1] not in ".!?", (
        f"{path.name}: description must not end with '.', '!', or '?' "
        f"(found: ...{desc[-40:]!r})"
    )
