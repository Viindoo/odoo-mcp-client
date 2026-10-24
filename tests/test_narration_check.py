"""`scripts/lib/narration_check.py` - a transcript is scored against the script with tones kept."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib"
sys.path.insert(0, str(LIB))
import narration_check as nc  # noqa: E402


def test_wer_ignores_case_and_punctuation_but_never_folds_diacritics():
    assert nc.wer("Xin chào, bạn!", "xin chào bạn") == 0.0
    assert nc.wer("ma má", "ma ma") == 0.5


def test_slots_accept_the_spoken_form_and_flag_an_ambiguous_acronym():
    pron = [{"written": "AI", "spoken": "ây ai"}]
    assert nc.slot_status(["AI", "Viindoo"], "trợ lý ây ai của viindoo", pron) == ([], [])
    missing, ambiguous = nc.slot_status(["AI"], "trợ lý AI của viindoo", pron)
    assert missing == [] and ambiguous == ["AI"]
    assert nc.slot_status(["Viindoo"], "trợ lý của ai đó", pron)[0] == ["Viindoo"]


def test_cli_verdicts_pass_fail_and_listen(tmp_path):
    script = tmp_path / "s.txt"
    script.write_text("Trợ lý AI của Viindoo giúp bạn bán hàng nhanh hơn.", encoding="utf-8")
    def run(transcript, *extra):
        t = tmp_path / "t.txt"
        t.write_text(transcript, encoding="utf-8")
        return subprocess.run([sys.executable, str(LIB / "narration_check.py"), "--script", str(script),
                               "--transcript", str(t), "--slots", "AI,Viindoo", *extra],
                              capture_output=True, text=True)
    nomap = run("trợ lý ây ai của viindoo giúp bạn bán hàng nhanh hơn")
    assert nomap.returncode == 3 and "SLOTS_AMBIGUOUS=AI" in nomap.stdout  # no map: "ai" may be the word "who"
    import json
    m = tmp_path / "map.json"
    m.write_text(json.dumps({"vi_VN": [{"written": "AI", "spoken": "ây ai"}]}, ensure_ascii=False),
                 encoding="utf-8")
    good = run("trợ lý ây ai của viindoo giúp bạn bán hàng nhanh hơn", "--map", str(m), "--lang", "vi_VN")
    assert good.returncode == 0 and "VERDICT=pass" in good.stdout
    listen = run("trợ lý AI của viindoo giúp bạn bán hàng nhanh hơn", "--map", str(m), "--lang", "vi_VN")
    assert listen.returncode == 3 and "VERDICT=listen" in listen.stdout
    bad = run("trợ lý ây ai của viindoo", "--map", str(m), "--lang", "vi_VN")
    assert bad.returncode == 1 and "VERDICT=fail" in bad.stdout


def test_a_sentence_that_runs_on_to_the_next_line_fails_the_script_check(tmp_path):
    assert nc.broken_lines("Mở đơn hàng.\nBấm Xác nhận!\n\nXong?") == []
    assert nc.broken_lines("Mở đơn hàng và\nbấm Xác nhận.\nXong rồi") == [1]  # last line may end bare
    assert nc.broken_lines("Một câu không dấu chấm") == []
    assert nc.broken_lines('He said "Done."\nNext line continues\nto here.') == [2]
    script = tmp_path / "s.txt"
    script.write_text("Trợ lý AI của Viindoo\ngiúp bạn bán hàng nhanh hơn.\n", encoding="utf-8")
    proc = subprocess.run([sys.executable, str(LIB / "narration_check.py"), "--script", str(script)],
                          capture_output=True, text=True)
    assert proc.returncode == 1 and "LINES_BROKEN=1" in proc.stdout and "VERDICT=fail" in proc.stdout
    script.write_text("Trợ lý AI của Viindoo giúp bạn bán hàng nhanh hơn.\n", encoding="utf-8")
    proc = subprocess.run([sys.executable, str(LIB / "narration_check.py"), "--script", str(script)],
                          capture_output=True, text=True)
    assert proc.returncode == 0 and "LINES_BROKEN=none" in proc.stdout
    # with a perfect transcript a broken script still fails
    script.write_text("Trợ lý AI của Viindoo\ngiúp bạn bán hàng nhanh hơn.\n", encoding="utf-8")
    t = tmp_path / "t.txt"
    t.write_text("trợ lý ây ai của viindoo giúp bạn bán hàng nhanh hơn", encoding="utf-8")
    proc = subprocess.run([sys.executable, str(LIB / "narration_check.py"), "--script", str(script),
                           "--transcript", str(t)], capture_output=True, text=True)
    assert proc.returncode == 1 and "VERDICT=fail" in proc.stdout


def test_a_sentence_longer_than_the_spoken_limit_fails_the_script_check(tmp_path):
    assert nc.long_sentences("Bạn mở đơn hàng. Bấm xác nhận.") == []
    longs = nc.long_sentences("Trong phần này chúng ta sẽ cùng nhau tìm hiểu cách mà hệ thống xử lý một đơn hàng từ lúc tạo cho đến khi xác nhận xong.", 15)
    assert len(longs) == 1 and longs[0][1] > 15
    script = tmp_path / "s.txt"
    script.write_text("Trong phần này chúng ta sẽ cùng nhau tìm hiểu cách mà hệ thống xử lý một đơn hàng từ lúc tạo cho đến khi xác nhận xong.\n", encoding="utf-8")
    proc = subprocess.run([sys.executable, str(LIB / "narration_check.py"), "--script", str(script)], capture_output=True, text=True)
    assert proc.returncode == 1 and "SENTENCES_LONG=1:" in proc.stdout and "LONG=1" in proc.stdout
    assert subprocess.run([sys.executable, str(LIB / "narration_check.py"), "--script", str(script), "--max-words", "0"],
                          capture_output=True, text=True).returncode == 0
