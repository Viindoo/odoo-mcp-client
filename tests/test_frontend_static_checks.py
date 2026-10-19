"""Behavioural guard for scripts/lib/frontend_static_checks.py (verify-frontend Tier 2).

Two reference checks that a green eslint run cannot give:

- a NEW `@module/path` import must name a file that exists (an import that does not resolve
  only fails at runtime, in the browser, after the module graph is built);
- an `<xpath position="before|after">` must not land between a `t-if` and the `t-else` that
  continues it, because the inserted node silently takes the chain over.

Tests assert on the findings a caller reads (severity, file:line, message), never on how the
helper walks the tree, so both XPath engines (lxml, or the stdlib fallback) must satisfy them.

Run with: python3 -m pytest tests/test_frontend_static_checks.py -v
"""
import importlib.util
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "frontend_static_checks.py"

_spec = importlib.util.spec_from_file_location("frontend_static_checks", LIB)
checks = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checks)


def _sh(cwd, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=cwd, check=True, capture_output=True,
    )


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


def _findings(capsys):
    return [ln.split("|", 2) for ln in capsys.readouterr().out.splitlines() if ln]


def _by(findings, sev):
    return [f for f in findings if f[0] == sev]


@pytest.fixture
def repo(tmp_path):
    """An addons repo with a committed module `other` (static/src/x.js, static/tests/h.js)."""
    r = tmp_path / "addons"
    r.mkdir()
    _write(r / "other" / "__manifest__.py", "{'name': 'o'}\n")
    _write(r / "other" / "static" / "src" / "x.js", "export const x = 1;\n")
    _write(r / "other" / "static" / "tests" / "h.js", "export const h = 1;\n")
    _write(r / "mine" / "__manifest__.py", "{'name': 'm'}\n")
    _write(r / "mine" / "static" / "src" / "old.js", "export const old = 1;\n")
    _sh(r, "init", "-q", "-b", "main")
    _sh(r, "add", "-A")
    _sh(r, "commit", "-q", "-m", "fixture")
    return r


def _imports(capsys, repo, *files, dirs=None):
    checks.check_imports([str(f) for f in files], [str(d) for d in (dirs or [repo])], "HEAD")
    return _findings(capsys)


# ---------------------------------------------------------------------------
# imports
# ---------------------------------------------------------------------------
def test_a_new_import_whose_module_exists_but_file_does_not_blocks(repo, capsys):
    """Fails if a dangling `@module/path` import is accepted."""
    js = _write(repo / "mine" / "static" / "src" / "new.js",
                '/** @odoo-module **/\nimport { a } from "@other/missing";\n')
    blocks = _by(_imports(capsys, repo, js), "BLOCK")
    assert len(blocks) == 1
    assert blocks[0][1].endswith("new.js:2")
    assert "import @other/missing does not resolve" in blocks[0][2]
    assert "other/static/src/missing(.js) missing" in blocks[0][2]


def test_an_import_resolving_to_static_src_passes(repo, capsys):
    """Fails if a resolvable import (with or without .js, multi-line or side-effect form)
    is reported."""
    js = _write(repo / "mine" / "static" / "src" / "new.js", """\
        import { a } from "@other/x";
        import {
            b,
        } from '@other/x.js';
        import "@other/x";
        const lazy = import("@other/x");
    """)
    assert [f for f in _imports(capsys, repo, js) if f[0] != "INFO"] == []


def test_a_tests_relative_import_resolves_through_the_parent(repo, capsys):
    """`@module/../tests/x` is how a test imports a helper that lives beside static/src."""
    js = _write(repo / "mine" / "static" / "tests" / "t.js",
                'import { h } from "@other/../tests/h";\n'
                'import { n } from "@other/../tests/nope";\n')
    blocks = _by(_imports(capsys, repo, js), "BLOCK")
    assert [b[1].rsplit(":", 1)[1] for b in blocks] == ["2"], (
        "only the missing helper may block; the existing one resolves via the parent dir"
    )


def test_an_import_of_a_module_outside_the_known_addons_is_never_a_block(repo, capsys):
    """Fails if an unavailable checkout turns every foreign import into a false BLOCK."""
    js = _write(repo / "mine" / "static" / "src" / "new.js",
                'import { m } from "@elsewhere/models/thing";\n')
    found = _imports(capsys, repo, js)
    assert _by(found, "BLOCK") == []
    assert [f[0] for f in found] == ["INFO"]
    assert "elsewhere" in found[0][2]


def test_only_added_import_lines_are_checked(repo, capsys):
    """A pre-existing dangling import is not this change's defect; the added one is."""
    js = repo / "mine" / "static" / "src" / "old.js"
    js.write_text('import { z } from "@other/pre_existing_gap";\nexport const old = 1;\n',
                  encoding="utf-8")
    _sh(repo, "add", "-A")
    _sh(repo, "commit", "-q", "-m", "legacy gap")
    js.write_text(js.read_text(encoding="utf-8") + 'import { q } from "@other/added_gap";\n',
                  encoding="utf-8")
    blocks = _by(_imports(capsys, repo, js), "BLOCK")
    assert len(blocks) == 1
    assert "added_gap" in blocks[0][2] and blocks[0][1].endswith("old.js:3")


def test_odoo_alias_imports_are_never_checked(repo, capsys):
    """`@odoo/owl` is a loader alias, not a module path - even when a dir named odoo exists."""
    (repo / "odoo").mkdir()
    js = _write(repo / "mine" / "static" / "src" / "new.js",
                'import { Component } from "@odoo/owl";\nimport "@odoo/hoot";\n')
    assert _imports(capsys, repo, js) == []


def test_import_check_cli_prints_block_lines_and_exits_zero(repo):
    js = _write(repo / "mine" / "static" / "src" / "new.js",
                'import { a } from "@other/missing";\n')
    res = subprocess.run(
        [sys.executable, str(LIB), "imports", "--addons-dir", str(repo), "--base", "HEAD", str(js)],
        capture_output=True, text=True, cwd=repo,
    )
    assert res.returncode == 0, res.stderr
    assert res.stdout.startswith("BLOCK|") and "new.js:1|" in res.stdout


# ---------------------------------------------------------------------------
# xpath-branch
# ---------------------------------------------------------------------------
CLIENT_BASE = """\
    <templates>
      <t t-name="web.Base">
        <div class="head" t-if="a">A</div>
        <div t-elif="b">B</div>
        <div t-else="">C</div>
        <p class="plain">tail</p>
      </t>
    </templates>
"""


def _client_ext(xpath_expr, position, inserted="<span>new</span>"):
    return f"""\
    <templates>
      <t t-name="ext.Base" t-inherit="web.Base" t-inherit-mode="extension">
        <xpath expr="{xpath_expr}" position="{position}">{inserted}</xpath>
      </t>
    </templates>
    """


@pytest.fixture
def addons(tmp_path):
    d = tmp_path / "addons"
    _write(d / "web" / "static" / "src" / "base.xml", CLIENT_BASE)
    _write(d / "web" / "views" / "base.xml", """\
        <odoo>
          <template id="base_tpl">
            <div t-if="a">A</div>
            <div t-else="">C</div>
          </template>
        </odoo>
    """)
    return d


def _xpath(capsys, addons, xml_text, name="ext/static/src/ext.xml"):
    f = _write(addons / name, xml_text)
    checks.check_xpath_branch([str(f)], [str(addons)])
    return _findings(capsys)


def test_inserting_after_a_t_if_whose_sibling_is_t_else_blocks(addons, capsys):
    """Fails if `after` on the node before a t-elif/t-else is accepted."""
    found = _xpath(capsys, addons, _client_ext("//div[@t-elif]", "after"))
    blocks = _by(found, "BLOCK")
    assert len(blocks) == 1 and blocks[0][1].endswith("ext.xml:3")
    assert "breaks the conditional chain" in blocks[0][2]
    assert "Inheriting QWeb templates" in blocks[0][2]


def test_inserting_before_a_t_else_blocks(addons, capsys):
    found = _xpath(capsys, addons, _client_ext("//div[@t-else]", "before"))
    assert len(_by(found, "BLOCK")) == 1


def test_inserting_a_t_elif_branch_into_the_chain_is_allowed(addons, capsys):
    """The one legitimate way to extend the chain: the inserted node is itself a t-elif."""
    found = _xpath(capsys, addons,
                   _client_ext("//div[@t-elif]", "after", '<div t-elif="c">new</div>'))
    assert _by(found, "BLOCK") == []


def test_inserting_outside_a_chain_or_inside_a_node_is_allowed(addons, capsys):
    after_plain = _xpath(capsys, addons, _client_ext("//p", "after"))
    inside = _xpath(capsys, addons, _client_ext("//div[@t-if]", "inside"))
    before_if = _xpath(capsys, addons, _client_ext("//div[@t-if]", "before"))
    assert _by(after_plain + inside + before_if, "BLOCK") == []


def test_an_unresolvable_inherited_template_warns_never_blocks(addons, capsys):
    xml = _client_ext("//div[@t-elif]", "after").replace("web.Base\" t-inherit-mode",
                                                         "web.Nowhere\" t-inherit-mode")
    found = _xpath(capsys, addons, xml)
    assert _by(found, "BLOCK") == []
    assert len(_by(found, "WARN")) == 1 and "web.Nowhere" in _by(found, "WARN")[0][2]


def test_an_unevaluable_xpath_warns_never_blocks(addons, capsys):
    found = _xpath(capsys, addons, _client_ext("//div[", "after"))
    assert _by(found, "BLOCK") == []
    assert len(_by(found, "WARN")) == 1


def test_an_xpath_matching_nothing_warns_never_blocks(addons, capsys):
    found = _xpath(capsys, addons, _client_ext("//section", "after"))
    assert _by(found, "BLOCK") == []
    assert "matches nothing" in _by(found, "WARN")[0][2]


def test_a_server_inherit_id_template_with_the_same_shape_blocks(addons, capsys):
    """The server QWeb (`inherit_id`) breaks the same way as the client `t-inherit`."""
    tpl = _xpath(capsys, addons, """\
        <odoo>
          <template id="ext_tpl" inherit_id="web.base_tpl">
            <xpath expr="//div[@t-if]" position="after"><span>x</span></xpath>
          </template>
        </odoo>
    """, name="ext/views/ext.xml")
    rec = _xpath(capsys, addons, """\
        <odoo>
          <record id="ext_view" model="ir.ui.view">
            <field name="inherit_id" ref="web.base_tpl"/>
            <field name="arch" type="xml">
              <data><xpath expr="//div[@t-else]" position="before"><span>x</span></xpath></data>
            </field>
          </record>
        </odoo>
    """, name="ext/views/ext2.xml")
    assert len(_by(tpl, "BLOCK")) == 1
    assert len(_by(rec, "BLOCK")) == 1


def test_xpath_branch_cli_prints_block_lines_and_exits_zero(addons):
    f = _write(addons / "ext" / "static" / "src" / "ext.xml",
               _client_ext("//div[@t-elif]", "after"))
    res = subprocess.run(
        [sys.executable, str(LIB), "xpath-branch", "--addons-dir", str(addons), str(f)],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stderr
    assert res.stdout.startswith("BLOCK|") and "ext.xml:3|" in res.stdout
