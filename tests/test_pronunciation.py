"""`scripts/lib/pronunciation.py` - a map rewrites whole tokens for the speech engine and nothing else.

The examples are the ones the narration requirement states: vi `AI -> ây ai` must not touch `ai`
("who"), sentence-initial `Ai` or substrings like `mai`; `AI,`, `AI.`, `(AI)` and `AI-first`
match; `AIRPORT` does not; all-capital text is left alone; the self-check fails loudly.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib"
sys.path.insert(0, str(LIB))
import pronunciation  # noqa: E402

VI = [{"written": "AI", "spoken": "ây ai"}, {"written": "Viindoo", "spoken": "Vin đu"}]


def test_whole_token_matches_with_punctuation_and_hyphen_boundaries():
    assert pronunciation.apply_map("AI, AI. (AI) AI-first", VI) == "ây ai, ây ai. (ây ai) ây ai-first"


def test_case_substring_and_underscore_neighbours_are_left_alone():
    assert pronunciation.apply_map("ai Ai mai AIRPORT AI_x", VI) == "ai Ai mai AIRPORT AI_x"


def test_tonal_text_around_the_token_is_untouched_and_nfc():
    out = pronunciation.apply_map("Trợ lý AI của Viindoo giúp bạn.", VI)
    assert out == "Trợ lý ây ai của Vin đu giúp bạn."


def test_all_capital_text_is_not_rewritten():
    assert pronunciation.apply_map("WELCOME TO THE AI DEMO TODAY", VI) == "WELCOME TO THE AI DEMO TODAY"


def test_phoneme_entries_apply_only_when_the_engine_supports_them():
    entries = [{"written": "Viindoo", "spoken": "<phoneme>vin.du</phoneme>", "kind": "phoneme"}]
    assert pronunciation.apply_map("Viindoo", entries) == "Viindoo"
    assert pronunciation.apply_map("Viindoo", entries, phonemes=True) == "<phoneme>vin.du</phoneme>"


def test_selfcheck_cli_fails_loudly_on_a_wrong_substitution(tmp_path):
    spec = {"vi_VN": VI, "_selfcheck": {"vi_VN": [
        {"in": "Ai dùng AI?", "out": "Ai dùng ây ai?"},
        {"in": "mai AI", "out": "mai ây ai"},
    ]}}
    f = tmp_path / "map.json"
    f.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    ok = subprocess.run([sys.executable, str(LIB / "pronunciation.py"), "selfcheck", "--map", str(f)],
                        capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
    spec["_selfcheck"]["vi_VN"].append({"in": "mai", "out": "mây ai"})
    f.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    bad = subprocess.run([sys.executable, str(LIB / "pronunciation.py"), "selfcheck", "--map", str(f)],
                         capture_output=True, text=True)
    assert bad.returncode == 1 and "mai" in bad.stderr


def test_two_mapped_terms_that_touch_get_a_pause_so_the_engine_never_merges_them():
    m = [{"written": "Viindoo", "spoken": "Vinn đu"}, {"written": "AI", "spoken": "ây ai"}]
    assert pronunciation.apply_map("Viindoo AI giúp bạn.", m) == "Vinn đu, ây ai giúp bạn."
    assert pronunciation.apply_map("Trợ lý AI của Viindoo", m) == "Trợ lý ây ai của Vinn đu"   # not adjacent: no pause
    assert pronunciation.apply_map("mai AIRPORT Ai ai AI_x", m) == "mai AIRPORT Ai ai AI_x"


def test_the_registry_wins_over_a_storyboard_map_and_the_map_may_only_add(tmp_path):
    reg = {"vi_VN": [{"written": "Viindoo", "spoken": "Vinn đu", "group": "brand", "confirmed": True}]}
    spec = {"vi_VN": [{"written": "Viindoo", "spoken": "Vi in đu"}, {"written": "Mistral", "spoken": "Mít xờ tran"}],
            "_selfcheck": {"vi_VN": []}}
    merged = pronunciation.merge(spec, reg)
    assert [e["written"] for e in merged["vi_VN"]] == ["Viindoo", "Mistral"]
    assert merged["vi_VN"][0]["spoken"] == "Vinn đu" and "_selfcheck" in merged


def test_registry_cli_round_trip_and_missing_terms(tmp_path):
    reg = tmp_path / "pronunciation.json"
    import subprocess, sys as _sys
    cli = [_sys.executable, str(LIB / "pronunciation.py"), "registry"]
    assert subprocess.run(cli + ["add", "--lang", "vi_VN", "--written", "Viindoo", "--spoken", "Vinn đu", "--group", "brand",
                                 "--registry-file", str(reg)], capture_output=True, text=True).returncode == 0
    listed = subprocess.run(cli + ["list", "--registry-file", str(reg)], capture_output=True, text=True).stdout
    assert "Viindoo\tVinn đu\trespell\tbrand\tunconfirmed" in listed
    assert subprocess.run(cli + ["confirm", "--lang", "vi_VN", "--written", "Viindoo", "--registry-file", str(reg)],
                          capture_output=True, text=True).returncode == 0
    assert "confirmed" in subprocess.run(cli + ["list", "--registry-file", str(reg)], capture_output=True, text=True).stdout.split("\t")[-1]
    text = tmp_path / "n.txt"
    text.write_text("Viindoo AI dùng Anthropic Claude và Mistral. Click Save. Trợ lý AI của Google Gemini.", encoding="utf-8")
    out = subprocess.run(cli + ["missing", "--lang", "vi_VN", "--text", str(text), "--registry-file", str(reg)],
                         capture_output=True, text=True).stdout
    assert "MISSING=Anthropic" in out and "MISSING=Mistral" in out and "MISSING=Viindoo" not in out
    assert subprocess.run(cli + ["remove", "--lang", "vi_VN", "--written", "Viindoo", "--registry-file", str(reg)],
                          capture_output=True, text=True).returncode == 0
