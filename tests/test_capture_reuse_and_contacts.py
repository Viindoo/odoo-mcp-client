"""Guards for the second follow-up PR: one capture instance per documentation tail, contact
details from the author profile, narration from a vendor-neutral speech configuration.

Each test reads the prose a runtime agent reads and fails when the rule it protects is gone.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"


def _read(rel):
    return (PLUGIN / rel).read_text(encoding="utf-8")


def _squash(text):
    return " ".join(text.split())


# --- one capture instance for the documentation tail ------------------------------------------


def test_the_docs_tail_forwards_one_capture_instance_and_the_owner_releases_it():
    snippet = _squash(_read("snippets/docs-after-change.md"))
    assert "One capture instance for the whole tail" in snippet
    assert "never builds an instance another step of the same run already built" in snippet
    assert "releases the handle once the last docs step returned" in snippet
    for rel, needle in (
        ("skills/odoo-doc-illustration/SKILL.md", "never a second lease"),
        ("skills/odoo-doc-site/SKILL.md", "provisions nothing"),
        ("skills/odoo-i18n/SKILL.md", "`HAND_ON: <skill>`"),
        ("snippets/instance-handle-contract.md", "Hand-on between consumers"),
        ("skills/odoo-forward-port/SKILL.md", "`HAND_ON: odoo-doc-illustration`"),
        ("skills/odoo-modules-upgrade/SKILL.md", "`HAND_ON: odoo-doc-illustration`"),
        ("skills/odoo-intake/references/plan-mode-schema.md", "share one capture instance"),
    ):
        assert needle in _squash(_read(rel)), (rel, needle)


def test_a_docs_step_never_releases_a_forwarded_handle():
    for rel in ("skills/odoo-doc-illustration/SKILL.md", "skills/odoo-doc-site/SKILL.md"):
        text = _squash(_read(rel))
        assert re.search(r"never a (forwarded `INSTANCE_HANDLE`|handle the caller forwarded)", text), rel


# --- published contact details ----------------------------------------------------------------


def test_the_store_template_links_contact_pages_and_carries_no_address():
    template = _read("skills/odoo-doc-illustration/references/app-store-template.md")
    assert "{{PRESALES_URL}}" in template and "{{SUPPORT_URL}}" in template
    assert "mailto:" not in template.split("## 3. Bootstrap-5 Fragment Skeleton")[1]
    assert "PRESALES_EMAIL" not in template and "SUPPORT_EMAIL" not in template
    assert "LINK_TEXT_HIDES_URL" in template
    refs = _read("snippets/module-doc-references.md")
    assert "LINK_MAILTO" in refs and "mailto:`, author-site and video links are fine" not in refs


def test_the_writers_take_contact_details_from_the_author_profile_only():
    marketer = _read("agents/odoo-marketer.md")
    assert "`AUTHOR PROFILE`" in marketer and "never filled from memory" in _squash(marketer)
    assert "email_image.py" in marketer
    deps = json.loads((PLUGIN / "generator/skill_tool_deps.json").read_text(encoding="utf-8"))
    assert "AUTHOR PROFILE" in deps["agents"]["odoo-marketer"]["brief"]["optional"]
    illustration = _read("skills/odoo-doc-illustration/SKILL.md")
    assert "author_profile_config.py show" in illustration
    contract = _read("snippets/public-docs-contract.md")
    assert "email_image.py" in contract and "LINK_TEXT_HIDES_URL" not in contract  # rule by meaning, not by code name
    assert "hides its URL" in contract


def test_setup_exposes_author_voice_and_youtube_steps_outside_all():
    setup = _read("commands/odoo-setup.md")
    assert "| `author`" in setup and "| `voice`" in setup and "| `youtube`" in setup
    assert "`65-author-profile`, `70-speech` and `75-youtube`" in setup
    for step in ("65-author-profile", "70-speech", "75-youtube"):
        assert (PLUGIN / ("scripts/setup-steps/%s.sh" % step)).exists()


def test_a_video_of_code_rides_the_pr_and_a_video_of_docs_goes_to_the_channel_last():
    tail = _read("snippets/video-destination.md")
    assert "# Where a video goes" in tail and "video-destination.md" in _read("snippets/docs-after-change.md")
    assert "pull request" in tail and "youtube.toml" in tail and "`youtube_upload`" in tail
    assert "after acceptance passed and the i18n reconcile" in tail
    assert "deleted when the run ends" in tail and "never committed" in tail
    workflow = _read("workflows/video-produce.workflow.yaml")
    assert "- id: publish" in workflow and workflow.index("- id: publish") > workflow.index("- id: assemble")
    assert "max_silence_s" in workflow and "One sentence never spans two lines" in workflow
    gh = (PLUGIN.parent / "git-toolkit/agents/github-operator.md").read_text(encoding="utf-8")
    assert "--attach" in gh and "alone in its own paragraph" in gh


def test_the_video_workflow_gates_narration_on_the_speech_configuration():
    wf = _read("workflows/video-produce.workflow.yaml")
    assert "70-speech.sh check" in wf and "- id: narrate" in wf
    assert "`speech_synthesize`" in wf and "`speech_transcribe`" in wf and "narration_check.py" in wf
    assert "speech_client.py" not in wf and "youtube_upload.py" not in wf  # the values live in the odoo-media server
    assert "`youtube_check`" in wf and "youtube:<purpose>" in wf
    assert "video_publish.py verify" in wf and "never ask for a key" in wf


def test_a_video_is_recorded_per_language_checked_before_recording_and_gated_before_upload():
    wf = _read("workflows/video-produce.workflow.yaml")
    assert "verify-tools" in wf and "registry missing" in wf and "{lang}-scene-N" in wf
    assert "listen" in wf and "youtube:<purpose>" in wf and "targets" in wf


def test_intake_and_the_planner_decide_a_workflow_input_never_the_yaml_default():
    assert "workflow_inputs" in _read("skills/odoo-intake/SKILL.md")
    assert "workflow_inputs" in _read("skills/odoo-intake/references/plan-mode-schema.md")
    assert "workflow_inputs" in _read("agents/odoo-planner.md") and "youtube_check" in _read("agents/odoo-planner.md")
    assert "video-produce" in _read("skills/odoo-intake/references/collision-zones.md")
    table = _read("skills/odoo-intake/references/routing-table.md")
    assert "publish" in table.split("| 36 |", 1)[1].split("\n", 1)[0]


def test_a_video_is_embedded_only_in_its_own_language():
    assert "narration language" in _read("snippets/video-destination.md")
    assert "Embedded video" in _read("skills/odoo-doc-site/references/acceptance.md")
    assert "VIDEOS:" in _read("skills/odoo-doc-site/references/writer-brief.md")
    assert "ENGLISH narration" in _read("skills/odoo-doc-illustration/references/app-store-template.md")
