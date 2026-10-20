"""Behavior tests for scripts/lib/docs_site/ui_terms.py - translated UI terms against a live instance.

A translated page that tells the reader to click "Orders" when the screen says "Don hang" is a
broken page. The helper pulls the terms a translation uses out of its msgstr and asks the instance, in
that language, whether it shows them. The instance here is a local fake that speaks the same
JSON-RPC (/web/session/authenticate, /web/dataset/call_kw), returns names by the language it is
asked in, and refuses a wrong login - so the tests need no Odoo, no database and no network.

Run with: python3 -m pytest tests/test_docs_site_ui_terms.py -q
"""
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib"
sys.path.insert(0, str(LIB))

from docs_site import ui_terms  # noqa: E402

SCRIPT = LIB / "docs_site" / "ui_terms.py"
ARROW = "‣"
SECRET = "s3cret-pw-for-tests"

LANGS = {"vi_VN": True, "fr_FR": False}
MENUS = {
    "vi_VN": [{"name": "Ban hang", "complete_name": "Ban hang"},
              {"name": "Don hang", "complete_name": "Ban hang / Don hang"}],
    "en_US": [{"name": "Sales", "complete_name": "Sales"},
              {"name": "Orders", "complete_name": "Sales / Orders"}],
}
ACTIONS = {"vi_VN": [{"name": "Bao gia"}], "en_US": [{"name": "Quotations"}]}
APPS = {"vi_VN": [{"shortdesc": "Quan ly kho"}], "en_US": [{"shortdesc": "Inventory"}]}


class FakeOdoo(BaseHTTPRequestHandler):
    seen_langs = []

    def log_message(self, *args):
        pass

    def _reply(self, result=None, error=None, cookie=False):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "result": result} if error is None
                          else {"jsonrpc": "2.0", "id": 1, "error": error}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        if cookie:
            self.send_header("Set-Cookie", "session_id=abc; Path=/")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        params = json.loads(self.rfile.read(int(self.headers["Content-Length"])))["params"]
        if self.path == "/web/session/authenticate":
            ok = params["login"] == "admin" and params["password"] == SECRET and params["db"] == "docs"
            return self._reply({"uid": 2 if ok else False}, cookie=ok)
        if "session_id=abc" not in (self.headers.get("Cookie") or ""):
            return self._reply(error={"message": "Session expired", "data": {"message": "Session expired"}})
        model, kw = params["model"], params["kwargs"]
        if model == "res.lang":
            code = params["args"][0][0][2]
            return self._reply([{"code": code, "active": LANGS[code]}] if code in LANGS else [])
        lang = kw["context"].get("lang", "en_US")
        FakeOdoo.seen_langs.append(lang)
        table = {"ir.ui.menu": MENUS, "ir.actions.act_window": ACTIONS, "ir.module.module": APPS}[model]
        domain = params["args"][0]
        if model == "ir.module.module" and not (["state", "=", "installed"] in domain
                                                and ["application", "=", True] in domain):
            return self._reply([])         # only installed applications have names worth checking
        return self._reply(table.get(lang, table["en_US"]))


@pytest.fixture
def odoo():
    FakeOdoo.seen_langs = []
    server = HTTPServer(("127.0.0.1", 0), FakeOdoo)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    yield "http://127.0.0.1:%d" % server.server_port
    server.shutdown()
    server.server_close()


def po_file(tmp_path, *msgstrs, name="page.po"):
    body = 'msgid ""\nmsgstr ""\n"Language: vi\\n"\n\n'
    for i, text in enumerate(msgstrs):
        body += 'msgid "src %d"\nmsgstr %s\n\n' % (i, json.dumps(text, ensure_ascii=False))
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def run(url, po, *extra, password=SECRET, lang="vi_VN", login="admin", db="docs"):
    env = {k: v for k, v in os.environ.items() if k != "ODOO_DOC_PASSWORD"}
    if password is not None:
        env["ODOO_DOC_PASSWORD"] = password
    args = [sys.executable, str(SCRIPT), "--url", url, "--db", db, "--login", login, "--lang", lang,
            "--po", str(po), "--json", *extra]
    return subprocess.run(args, capture_output=True, text=True, env=env, timeout=60)


# ----------------------------------------------------------------------------- extraction

def terms(text):
    return [(t, k) for t, k, _p in ui_terms.extract_terms(text)]


def test_a_bold_menu_path_is_split_on_the_arrow_into_its_parts():
    assert terms("Vao **Ban hang %s Don hang** de xem." % ARROW) == [("Ban hang", "menu"), ("Don hang", "menu")]


def test_a_bold_menu_path_is_also_split_on_a_spaced_greater_than():
    assert terms("Go to **Sales > Orders > Quotations**.") == [
        ("Sales", "menu"), ("Orders", "menu"), ("Quotations", "menu")]


def test_a_bold_word_without_a_separator_is_not_a_menu_term():
    assert terms("This is **important** and **a>b** only.") == []


def test_guilabel_and_menuselection_parts_are_terms():
    got = terms("Click :guilabel:`Luu` then :menuselection:`Ban hang --> Don hang`.")
    assert got == [("Ban hang", "menu"), ("Don hang", "menu"), ("Luu", "guilabel")]


def test_terms_from_po_ignore_the_header_and_remember_where_each_came_from(tmp_path):
    po = po_file(tmp_path, "**Ban hang %s Don hang**" % ARROW, ":guilabel:`Don hang`")
    got = ui_terms.terms_from_po([str(po)])
    assert sorted(got) == ["Ban hang", "Don hang"]
    assert got["Don hang"]["kinds"] == ["menu", "guilabel"]
    assert got["Don hang"]["paths"] == ["Ban hang / Don hang"]
    assert all(ref.startswith("page.po:") for ref in got["Don hang"]["files"])


def test_the_po_header_is_not_a_translation(tmp_path):
    path = tmp_path / "h.po"
    path.write_text('msgid ""\nmsgstr ""\n"X-Note: :guilabel:`Header term`\\n"\n', encoding="utf-8")
    assert ui_terms.terms_from_po([str(path)]) == {}


# ----------------------------------------------------------------------------- matching

CATALOG = {"ir.ui.menu.name": ["Ban hang", "Don hang"],
           "ir.ui.menu.complete_name": ["Ban hang", "Ban hang / Don hang"],
           "ir.actions.act_window.name": ["Bao gia"], "ir.module.module.shortdesc": ["Quan ly kho"]}


def test_a_term_is_found_exactly_then_case_insensitively_else_not_found():
    wanted = {t: {"term": t, "kinds": ["menu"], "files": [], "paths": []}
              for t in ("Don hang", "DON HANG", "Quan ly kho", "Nothing")}
    rows = {r["term"]: r for r in ui_terms.match_terms(wanted, CATALOG)}
    assert (rows["Don hang"]["found"], rows["Don hang"]["match"]) == (True, "exact")
    assert (rows["DON HANG"]["found"], rows["DON HANG"]["match"]) == (True, "case-insensitive")
    assert rows["Quan ly kho"]["sources"] == ["ir.module.module.shortdesc"]
    assert rows["Nothing"]["found"] is False and rows["Nothing"]["sources"] == []


# ----------------------------------------------------------------------------- against the fake instance

def test_every_term_found_in_the_requested_language_exits_0(odoo, tmp_path):
    po = po_file(tmp_path, "**Ban hang %s Don hang**" % ARROW, ":guilabel:`Bao gia`", ":guilabel:`Quan ly kho`")
    res = run(odoo, po)
    assert res.returncode == 0, res.stdout + res.stderr
    report = json.loads(res.stdout)
    assert report["ok"] is True and report["not_found"] == 0 and report["found"] == 4
    assert set(FakeOdoo.seen_langs) == {"vi_VN"}          # the instance was asked in that language


def test_a_term_the_instance_does_not_show_exits_1_and_is_listed(odoo, tmp_path):
    po = po_file(tmp_path, "**Ban hang %s Phieu gia**" % ARROW)
    res = run(odoo, po)
    assert res.returncode == 1
    report = json.loads(res.stdout)
    assert [r["term"] for r in report["terms"] if not r["found"]] == ["Phieu gia"]
    assert "NOT FOUND 'Phieu gia'" in res.stderr


def test_an_english_term_is_not_found_when_the_page_is_vietnamese(odoo, tmp_path):
    po = po_file(tmp_path, "**Sales %s Orders**" % ARROW)
    assert run(odoo, po).returncode == 1


def test_a_wrong_password_exits_2_and_the_password_is_never_printed(odoo, tmp_path):
    po = po_file(tmp_path, "**Ban hang %s Don hang**" % ARROW)
    res = run(odoo, po, password="wrong-pw-xyz")
    assert res.returncode == 2
    assert "login refused" in res.stderr
    assert "wrong-pw-xyz" not in res.stdout + res.stderr


def test_the_password_is_not_printed_on_success_either(odoo, tmp_path):
    po = po_file(tmp_path, "**Ban hang %s Don hang**" % ARROW)
    res = run(odoo, po)
    assert SECRET not in res.stdout + res.stderr


def test_without_the_password_variable_the_run_stops_before_any_request(odoo, tmp_path):
    po = po_file(tmp_path, "**Ban hang %s Don hang**" % ARROW)
    res = run(odoo, po, password=None)
    assert res.returncode == 2
    assert "ODOO_DOC_PASSWORD" in res.stderr
    assert FakeOdoo.seen_langs == []


def test_a_password_cannot_be_given_as_an_argument(odoo, tmp_path):
    po = po_file(tmp_path, "**Ban hang %s Don hang**" % ARROW)
    res = run(odoo, po, "--password", SECRET)          # the environment variable is set as well
    assert res.returncode == 2
    assert FakeOdoo.seen_langs == []


def test_a_language_that_is_not_active_on_the_instance_exits_2_not_a_false_not_found(odoo, tmp_path):
    po = po_file(tmp_path, "**Ban hang %s Don hang**" % ARROW)
    res = run(odoo, po, lang="fr_FR")
    assert res.returncode == 2
    assert "not installed and active" in res.stderr


def test_an_unreachable_instance_exits_2(tmp_path):
    po = po_file(tmp_path, "**A %s B**" % ARROW)
    assert run("http://127.0.0.1:1", po).returncode == 2


def test_the_menu_arrow_is_defined_once_and_the_docs_site_sources_stay_ascii():
    import docs_site
    from docs_site import repo_facts
    assert docs_site.ARROW == "‣" and ui_terms.ARROW is docs_site.ARROW
    assert repo_facts.ARROW is docs_site.ARROW
    for path in sorted((LIB / "docs_site").glob("*.py")):
        path.read_text(encoding="utf-8").encode("ascii")     # raises on a literal non-ASCII character
