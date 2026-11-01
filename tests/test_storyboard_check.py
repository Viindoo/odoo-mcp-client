"""`scripts/lib/storyboard_check.py` - the storyboard is validated, rendered and compiled from data."""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "storyboard_check.py"
FAKE_KEY = "sk-test-0123456789-not-a-real-key"

STORYBOARD = {
    "title": "Create a Quote",
    "video_type": "tutorial",
    "languages": ["en_US", "vi_VN"],
    "language_switch": [{"do": "goto", "url": "/web?lang={lang}"}],
    "wait_selectors": [".o_loading"],
    "ai": {"requests_per_scene": 2, "tokens_per_request": 500, "takes": 2, "trials_k": 3,
           "key_env": "DEMO_AI_KEY", "key_scope": "dedicated", "quota_note": "Daily quota applies."},
    "music": {"on": False},
    "scenes": [
        {"id": "intro", "title": {"en_US": "Intro", "vi_VN": "Mo dau"}, "click_path": ["Open the app"],
         "target_seconds": 8, "narration": {"en_US": "Welcome.", "vi_VN": "Xin chao."}},
        {"id": "quote", "title": {"en_US": "Quote", "vi_VN": "Bao gia"},
         "click_path": ["Open Sales",
                        {"do": "click", "selector": ".o_menu_sales"},
                        {"do": "fill", "selector": "input.name", "text": "Acme"}],
         "target_seconds": 20, "narration": {"en_US": "Create a quote.", "vi_VN": "Tao bao gia."},
         "must_see": [[2, 10]],
         "voice_input": {"en_US": "hello", "vi_VN": "xin chao"},
         "prompts": {"en_US": ["a", "b"], "vi_VN": ["c", "d"]}},
    ],
    "publish": {"en_US": {"title": "Quote", "description": "How."},
                "vi_VN": {"title": "Bao gia", "description": "Cach."}},
}


def _tool(*args, env=None):
    return subprocess.run([sys.executable, str(TOOL), *args], capture_output=True, text=True,
                          timeout=60, env=env)


def _kv(stdout):
    return dict(line.split("=", 1) for line in stdout.splitlines() if "=" in line)


def _write(tmp_path, sb, name="sb.json"):
    path = tmp_path / name
    path.write_text(json.dumps(sb, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _check(tmp_path, mutate):
    sb = copy.deepcopy(STORYBOARD)
    mutate(sb)
    proc = _tool("check", "--storyboard", _write(tmp_path, sb))
    return proc, [ln for ln in proc.stdout.splitlines() if ln.startswith("ERROR=")]


def test_valid_two_language_storyboard_passes_and_reports_text_only_scenes(tmp_path):
    proc = _tool("check", "--storyboard", _write(tmp_path, STORYBOARD))
    assert proc.returncode == 0, proc.stdout
    kv = _kv(proc.stdout)
    assert kv["OK"] == "1" and kv["SCENES"] == "2" and kv["LANGUAGES"] == "en_US,vi_VN"
    assert kv["ACTIONS"] == "2" and kv["TEXT_ONLY_SCENES"] == "intro"


def test_missing_narration_for_a_language_is_an_error_naming_the_path(tmp_path):
    proc, errors = _check(tmp_path, lambda sb: sb["scenes"][1]["narration"].pop("vi_VN"))
    assert proc.returncode == 1
    assert any(e.startswith("ERROR=scenes[1].narration.vi_VN: missing") for e in errors)
    assert _kv(proc.stdout)["ERRORS"] == str(len(errors))


def test_prompt_chosen_outside_prompts_is_an_error(tmp_path):
    proc, errors = _check(tmp_path, lambda sb: sb["scenes"][1].update(prompt_chosen={"en_US": "zzz"}))
    assert proc.returncode == 1
    assert any("scenes[1].prompt_chosen.en_US" in e for e in errors)


def test_a_shared_ai_key_is_an_error(tmp_path):
    proc, errors = _check(tmp_path, lambda sb: sb["ai"].update(key_scope="shared"))
    assert proc.returncode == 1
    assert any("a shared key never drives a demo" in e for e in errors)


def test_must_see_outside_the_target_is_an_error(tmp_path):
    proc, errors = _check(tmp_path, lambda sb: sb["scenes"][1].update(must_see=[[15, 25]]))
    assert proc.returncode == 1
    assert any("scenes[1].must_see[0]" in e for e in errors)


def test_two_languages_without_language_switch_is_an_error(tmp_path):
    def drop(sb):
        del sb["language_switch"]

    proc, errors = _check(tmp_path, drop)
    assert proc.returncode == 1
    assert any(e.startswith("ERROR=language_switch:") for e in errors)


def test_voice_in_without_voice_input_for_every_language_is_an_error(tmp_path):
    def break_voice(sb):
        sb["scenes"][1]["click_path"].append({"do": "voice_in"})
        del sb["scenes"][1]["voice_input"]["vi_VN"]

    proc, errors = _check(tmp_path, break_voice)
    assert proc.returncode == 1
    assert any("voice_input.vi_VN" in e for e in errors)


def test_render_lists_every_scene_and_narration_and_never_the_key_value(tmp_path):
    env = dict(os.environ, DEMO_AI_KEY=FAKE_KEY)
    out = tmp_path / "plan.md"
    proc = _tool("render", "--storyboard", _write(tmp_path, STORYBOARD), "--out", str(out), env=env)
    assert proc.returncode == 0, proc.stdout
    assert _kv(proc.stdout)["OUT"] == str(out)
    text = out.read_text(encoding="utf-8")
    for needle in ("intro", "quote", "Welcome.", "Xin chao.", "Create a quote.", "Tao bao gia.",
                   "DEMO_AI_KEY", "2-10s"):
        assert needle in text
    assert FAKE_KEY not in text


def test_scene_script_keeps_language_switch_out_of_actions_and_drops_human_strings(tmp_path):
    out = tmp_path / "script.json"
    proc = _tool("scene-script", "--storyboard", _write(tmp_path, STORYBOARD), "--lang", "vi_VN",
                 "--scene", "quote", "--base-url", "http://localhost:8069", "--out", str(out),
                 "--takes-dir", str(tmp_path / "takes"), "--ui-user", "demo")
    assert proc.returncode == 0, proc.stdout
    script = json.loads(out.read_text(encoding="utf-8"))
    assert script["language_switch"] == [{"do": "goto", "url": "/web?lang=vi_VN"}]
    assert script["actions"] == [
        {"do": "click", "selector": ".o_menu_sales"},
        {"do": "fill", "selector": "input.name", "text": "Acme"}]
    assert script["clip_name"] == "scene-quote" and script["label"] == "create-a-quote"
    assert script["wait_selectors"] == [".o_loading"] and script["must_see"] == [[2, 10]]
    assert script["ui_user"] == "demo" and script["out_dir"] == str(tmp_path / "takes")
    assert "user" not in script
    assert script["voice_wav"] is None and script["viewport"] == [1920, 1080]


def test_scene_script_voice_in_carries_the_wav_and_needs_one(tmp_path):
    sb = copy.deepcopy(STORYBOARD)
    sb["scenes"][1]["click_path"].append({"do": "voice_in"})
    path = _write(tmp_path, sb)
    base = ["scene-script", "--storyboard", path, "--lang", "en_US", "--scene", "quote",
            "--base-url", "http://x", "--out", str(tmp_path / "s.json")]
    refused = _tool(*base)
    assert refused.returncode == 1 and "ERROR=" in refused.stdout
    ok = _tool(*base, "--voice-wav", "/w/a.wav")
    assert ok.returncode == 0, ok.stdout
    script = json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))
    assert script["actions"][-1] == {"do": "voice_in", "wav": "/w/a.wav"}
    assert script["voice_wav"] == "/w/a.wav"


def test_scene_script_refuses_a_scene_with_no_action_object(tmp_path):
    out = tmp_path / "script.json"
    proc = _tool("scene-script", "--storyboard", _write(tmp_path, STORYBOARD), "--lang", "en_US",
                 "--scene", "intro", "--base-url", "http://x", "--out", str(out))
    assert proc.returncode == 1 and "ERROR=" in proc.stdout
    assert not out.exists()


def test_set_prompt_records_the_choice_and_refuses_an_unknown_prompt(tmp_path):
    path = _write(tmp_path, STORYBOARD)
    ok = _tool("set-prompt", "--storyboard", path, "--scene", "quote", "--lang", "vi_VN", "--prompt", "d")
    assert ok.returncode == 0 and _kv(ok.stdout)["OK"] == "1"
    raw = Path(path).read_text(encoding="utf-8")
    assert json.loads(raw)["scenes"][1]["prompt_chosen"] == {"vi_VN": "d"}
    assert raw.endswith("}\n") and '\n  "title"' in raw
    bad = _tool("set-prompt", "--storyboard", path, "--scene", "quote", "--lang", "vi_VN", "--prompt", "nope")
    assert bad.returncode == 1
    assert json.loads(Path(path).read_text(encoding="utf-8"))["scenes"][1]["prompt_chosen"] == {"vi_VN": "d"}


def test_demo_data_script_refuses_an_empty_demo_data_and_compiles_a_filled_one(tmp_path):
    out = tmp_path / "prep.json"
    args = ["demo-data-script", "--base-url", "http://x", "--out", str(out)]
    for sb in (copy.deepcopy(STORYBOARD), dict(copy.deepcopy(STORYBOARD), demo_data=[])):
        proc = _tool(*args, "--storyboard", _write(tmp_path, sb))
        assert proc.returncode == 1 and "ERROR=" in proc.stdout
    filled = dict(copy.deepcopy(STORYBOARD), demo_data=[{"do": "goto", "url": "/web#seed"}])
    proc = _tool(*args, "--storyboard", _write(tmp_path, filled))
    assert proc.returncode == 0, proc.stdout
    script = json.loads(out.read_text(encoding="utf-8"))
    assert script["clip_name"] == "prepare" and script["actions"] == [{"do": "goto", "url": "/web#seed"}]


def test_set_language_is_not_an_action(tmp_path):
    proc, errors = _check(tmp_path, lambda sb: sb["scenes"][1]["click_path"].insert(1, {"do": "set_language"}))
    assert proc.returncode == 1
    assert ("ERROR=scenes[1].click_path[1]: set_language is not an action - the recorder switches the "
            "language before every take from language_switch") in errors


def test_wait_for_timeout_s_must_be_a_positive_number(tmp_path):
    def wait(value):
        return lambda sb: sb["scenes"][1]["click_path"].append(
            {"do": "wait_for", "selector": ".x", "state": "visible", "timeout_s": value})

    for bad in (0, -3, "5"):
        proc, errors = _check(tmp_path, wait(bad))
        assert proc.returncode == 1, bad
        assert any(".timeout_s: must be a number > 0" in e for e in errors), (bad, errors)
    proc, _ = _check(tmp_path, wait(2.5))
    assert proc.returncode == 0, proc.stdout


def _silent(languages):
    sb = {"title": "Quiet", "video_type": "tutorial", "languages": languages,
          "scenes": [{"id": "a", "title": {}, "click_path": [{"do": "goto", "url": "/web"}], "target_seconds": 5},
                     {"id": "b", "title": {}, "click_path": [{"do": "hold", "seconds": 1}], "target_seconds": 5}]}
    return sb


def test_empty_languages_is_a_silent_video_needing_no_narration(tmp_path):
    path = _write(tmp_path, _silent([]))
    proc = _tool("check", "--storyboard", path)
    assert proc.returncode == 0, proc.stdout
    kv = _kv(proc.stdout)
    assert kv["LANGUAGES"] == "" and kv["SILENT"] == "1"
    out = tmp_path / "s.json"
    ok = _tool("scene-script", "--storyboard", path, "--lang", "en_US", "--scene", "a",
               "--base-url", "http://x", "--out", str(out))
    assert ok.returncode == 0, ok.stdout
    assert json.loads(out.read_text(encoding="utf-8"))["lang"] == "en_US"
    assert _tool("scene-script", "--storyboard", path, "--lang", "english", "--scene", "a",
                 "--base-url", "http://x", "--out", str(out)).returncode == 1
    plan = tmp_path / "plan.md"
    assert _tool("render", "--storyboard", path, "--out", str(plan)).returncode == 0
    assert "Silent video (no narration)" in plan.read_text(encoding="utf-8")


def test_empty_languages_still_refuses_language_keyed_data(tmp_path):
    sb = _silent([])
    sb["scenes"][0]["prompts"] = {"en_US": ["a"]}
    proc = _tool("check", "--storyboard", _write(tmp_path, sb))
    assert proc.returncode == 1 and "prompts.en_US: language not in `languages`" in proc.stdout


def test_narration_is_still_required_once_a_language_is_listed(tmp_path):
    proc = _tool("check", "--storyboard", _write(tmp_path, _silent(["en_US"])))
    assert proc.returncode == 1
    assert "ERROR=scenes[0].narration: missing" in proc.stdout


def _labelled(sb):
    sb["language_switch"] = [{"do": "select", "selector": "#lang", "value": "{lang_label}"}]
    sb["language_labels"] = {"en_US": "English (US)", "vi_VN": "Vietnamese / Tieng Viet"}


def test_language_label_reaches_language_switch_and_demo_data_in_both_scripts(tmp_path):
    sb = copy.deepcopy(STORYBOARD)
    _labelled(sb)
    sb["demo_data"] = [{"do": "fill", "selector": "#l", "text": "{lang_label} / {lang}"}]
    path = _write(tmp_path, sb)
    out = tmp_path / "s.json"
    proc = _tool("scene-script", "--storyboard", path, "--lang", "vi_VN", "--scene", "quote",
                 "--base-url", "http://x", "--out", str(out))
    assert proc.returncode == 0, proc.stdout
    assert json.loads(out.read_text(encoding="utf-8"))["language_switch"] == [
        {"do": "select", "selector": "#lang", "value": "Vietnamese / Tieng Viet"}]
    proc = _tool("demo-data-script", "--storyboard", path, "--base-url", "http://x", "--out", str(out))
    assert proc.returncode == 0, proc.stdout
    assert json.loads(out.read_text(encoding="utf-8"))["actions"][0]["text"] == "English (US) / en_US"


def test_language_label_without_a_label_or_for_an_unlisted_language_is_an_error(tmp_path):
    def drop(sb):
        _labelled(sb)
        del sb["language_labels"]["vi_VN"]

    proc, errors = _check(tmp_path, drop)
    assert proc.returncode == 1
    assert "ERROR=language_labels.vi_VN: needed by language_switch" in errors

    def extra(sb):
        _labelled(sb)
        sb["language_labels"]["fr_FR"] = "Francais"

    proc, errors = _check(tmp_path, extra)
    assert proc.returncode == 1
    assert any(e.startswith("ERROR=language_labels.fr_FR:") for e in errors)
    proc, _ = _check(tmp_path, _labelled)
    assert proc.returncode == 0, proc.stdout


def _named_fill(sb):
    sb["scenes"][1]["click_path"][2]["text"] = {"en_US": "Office Chair", "vi_VN": "Ghe van phong"}
    sb["scenes"][1]["click_path"].append({"do": "select", "selector": "#s", "value": {"en_US": "A", "vi_VN": "B"}})


def test_fill_text_and_select_value_may_be_a_map_resolved_per_language(tmp_path):
    sb = copy.deepcopy(STORYBOARD)
    _named_fill(sb)
    path = _write(tmp_path, sb)
    out = tmp_path / "s.json"
    for lang, name, value in (("vi_VN", "Ghe van phong", "B"), ("en_US", "Office Chair", "A")):
        proc = _tool("scene-script", "--storyboard", path, "--lang", lang, "--scene", "quote",
                     "--base-url", "http://x", "--out", str(out))
        assert proc.returncode == 0, proc.stdout
        actions = json.loads(out.read_text(encoding="utf-8"))["actions"]
        assert actions[1]["text"] == name and actions[2]["value"] == value


def test_a_text_map_missing_a_listed_language_is_an_error(tmp_path):
    def broken(sb):
        _named_fill(sb)
        del sb["scenes"][1]["click_path"][2]["text"]["vi_VN"]

    proc, errors = _check(tmp_path, broken)
    assert proc.returncode == 1
    assert "ERROR=scenes[1].click_path[2].text.vi_VN: missing" in errors


def test_render_shows_the_language_switch_labels_and_wait_indicators(tmp_path):
    sb = copy.deepcopy(STORYBOARD)
    _labelled(sb)
    out = tmp_path / "plan.md"
    assert _tool("render", "--storyboard", _write(tmp_path, sb), "--out", str(out)).returncode == 0
    text = out.read_text(encoding="utf-8")
    assert "## Language switch" in text and "vi_VN: Vietnamese / Tieng Viet" in text
    assert 'select #lang "{lang_label}"' in text
    assert "Wait indicators: .o_loading" in text
    del sb["wait_selectors"]
    del sb["language_switch"]
    assert _tool("render", "--storyboard", _write(tmp_path, sb), "--out", str(out)).returncode == 0
    text = out.read_text(encoding="utf-8")
    assert "Wait indicators: the web client's own" in text and "Language switch: none" in text


# --------------------------------------------------------------------------- wait_squeeze_s
def _scene_script(tmp_path, sb):
    out = tmp_path / "ws.json"
    proc = _tool("scene-script", "--storyboard", _write(tmp_path, sb), "--lang", "en_US",
                 "--scene", "quote", "--base-url", "http://x", "--out", str(out))
    assert proc.returncode == 0, proc.stdout
    return json.loads(out.read_text(encoding="utf-8"))


def test_wait_squeeze_s_must_be_a_number_of_seconds_not_below_zero(tmp_path):
    for bad in (-1, "2", None):
        proc, errors = _check(tmp_path, lambda sb, v=bad: sb.__setitem__("wait_squeeze_s", v))
        assert proc.returncode == 1, bad
        assert any(e.startswith("ERROR=wait_squeeze_s") for e in errors), (bad, errors)
    for good in (0, 0.5, 3):
        proc, _ = _check(tmp_path, lambda sb, v=good: sb.__setitem__("wait_squeeze_s", v))
        assert proc.returncode == 0, good


def test_wait_squeeze_s_is_shown_by_render_and_carried_into_the_scene_script(tmp_path):
    sb = copy.deepcopy(STORYBOARD)
    sb["wait_squeeze_s"] = 2.5
    out = tmp_path / "plan.md"
    assert _tool("render", "--storyboard", _write(tmp_path, sb), "--out", str(out)).returncode == 0
    assert "wait_squeeze_s: 2.5" in out.read_text(encoding="utf-8")
    assert _scene_script(tmp_path, sb)["wait_squeeze_s"] == 2.5


def test_an_absent_wait_squeeze_s_is_one_second_in_the_scene_script(tmp_path):
    assert "wait_squeeze_s" not in STORYBOARD
    assert _scene_script(tmp_path, copy.deepcopy(STORYBOARD))["wait_squeeze_s"] == 1.0
