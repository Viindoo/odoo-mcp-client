"""Behavioural guard for scripts/lib/frontend_static_checks.py (verify-frontend Tier 2).

Three checks that a green eslint run cannot give:

- a NEW `@module/path` import must name a file that exists (an import that does not resolve
  only fails at runtime, in the browser, after the module graph is built);
- an `<xpath position="before|after">` must not land between a `t-if` and the `t-else` that
  continues it, because the inserted node silently takes the chain over;
- a change must not fix a colour scheme: no literal colour or scheme-fixing class on an added
  line, and every `*.dark.scss` registered in a `*_dark` bundle and out of the light ones, so a
  theme can restyle the module and core's dark bundle applies.

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


# ---------------------------------------------------------------------------
# scheme: a change must not fix a colour scheme (snippets/odoo-ui-contract.md § 2)
# ---------------------------------------------------------------------------
LIGHT_AND_DARK = {
    "web.assets_backend": ["mymod/static/src/**/*.scss",
                           ("remove", "mymod/static/src/**/*.dark.scss")],
    "web.assets_web_dark": ["mymod/static/src/**/*.dark.scss"],
}
DARK_SHEET = "--mymod-bg: #{mix($gray-100, $o-view-background-color)};\n"
SCHEME_CLASSES = [
    "bg-white", "bg-light", "bg-dark", "bg-black", "text-dark", "text-white", "text-black",
    "text-light", "border-light", "border-dark", "border-white",
]


def _scheme(capsys, *files, odoo_root=None):
    checks.check_scheme([str(f) for f in files], "HEAD", odoo_root)
    return _findings(capsys)


def _module(root, assets, name="mymod", manifest=None):
    text = manifest if manifest is not None else "{'name': 'm', 'assets': %r}\n" % (assets,)
    _write(root / name / "__manifest__.py", text)
    return root / name


def _sheet(repo, text, name="panel.scss"):
    return _write(repo / "mine" / "static" / "src" / name, text)


def _view(repo, tag):
    return _write(repo / "mine" / "views" / "v.xml",
                  f'<odoo>\n  <template id="t">\n    {tag}\n  </template>\n</odoo>\n')


def _lines(findings):
    return [f[1].rsplit(":", 1)[1] for f in findings]


@pytest.mark.parametrize("value", [
    "#fff", "#FFFFFF", "#ffffff80", "rgb(255, 255, 255)", "rgba(0, 0, 0, .5)",
    "hsl(210, 10%, 50%)", "hsla(210 10% 50% / .5)", "white", "black",
    "1px solid #ccc", "mix(white, $o-brand-primary, 10%)",
])
def test_a_literal_colour_in_an_added_stylesheet_line_warns(repo, capsys, value):
    """Fails if a colour fixed to one scheme is accepted in a stylesheet."""
    css = _sheet(repo, f".o_panel {{\n    border: {value};\n}}\n")
    warns = _by(_scheme(capsys, css), "WARN")
    assert len(warns) == 1 and warns[0][1].endswith("panel.scss:2")
    assert "odoo-ui-contract.md" in warns[0][2]


@pytest.mark.parametrize("line", [
    "color: $o-gray-700;",
    "color: $white;",
    "color: var(--mymod-fg);",
    "background-color: var(--mail-Composer-bg, $o-view-background-color);",
    "background-color: rgba($o-gray-900, .5);",
    "color: transparent;",
    "color: currentColor;",
    "color: inherit;",
    "--mymod-bg: #{mix($gray-100, $o-view-background-color)};",
    "content: 'white #fff';",
    "background: url(data:image/svg+xml;utf8,<svg fill='#fff'/>);",
    "// color: #fff;",
    "/* color: rgb(0, 0, 0); */",
    "@include button-variant($o-brand-primary);",
])
def test_core_levers_and_commented_colours_in_a_stylesheet_are_not_findings(repo, capsys, line):
    """Fails if a variable, var(), a keyword, a string, a comment or a colour derived from a
    variable is reported as a literal colour."""
    css = _sheet(repo, f".o_panel {{\n    {line}\n}}\n")
    assert _scheme(capsys, css) == []


def test_a_colour_inside_a_multi_line_comment_or_a_selector_is_not_a_finding(repo, capsys):
    css = _sheet(repo, """\
        /*
         * legacy value was #fff,
         * rgba(0, 0, 0, .5) before
         */
        #fade, .bg-white-label {
            padding: 0;
        }
    """)
    assert _scheme(capsys, css) == []


def test_only_the_lines_a_change_adds_are_checked(repo, capsys):
    """A literal colour that was already committed is not this change's defect."""
    css = _sheet(repo, ".o_old {\n    color: #111;\n}\n")
    _sh(repo, "add", "-A")
    _sh(repo, "commit", "-q", "-m", "legacy colour")
    css.write_text(css.read_text(encoding="utf-8") + ".o_new {\n    color: #222;\n}\n",
                   encoding="utf-8")
    assert _lines(_by(_scheme(capsys, css), "WARN")) == ["5"]


def test_an_untracked_file_is_checked_in_full(repo, capsys):
    css = _sheet(repo, ".a {\n    color: #111;\n}\n.b {\n    color: #222;\n}\n")
    assert _lines(_by(_scheme(capsys, css), "WARN")) == ["2", "5"]


def test_a_dark_sheet_may_hold_literal_colours(repo, capsys):
    """The dark file is where a scheme-specific value belongs."""
    _module(repo, LIGHT_AND_DARK)
    dark = _write(repo / "mymod" / "static" / "src" / "panel.dark.scss", "--mymod-bg: #1a1a1a;\n")
    assert _by(_scheme(capsys, dark), "WARN") == []


@pytest.mark.parametrize("attr, value", [
    ("style", "color: #fff"),
    ("style", "padding: 0; background-color: rgb(1, 2, 3)"),
    ("style", "border:1px solid white"),
    ("t-att-style", "'color: #000'"),
    ("t-attf-style", "background: #f5f5f5; width: #{w}px"),
])
def test_a_style_attribute_fixing_a_colour_warns(repo, capsys, attr, value):
    """Fails if a literal colour in a view or template style attribute is accepted."""
    xml = _view(repo, f'<div {attr}="{value}">x</div>')
    warns = _by(_scheme(capsys, xml), "WARN")
    assert len(warns) == 1 and warns[0][1].endswith("v.xml:3")
    assert "odoo-ui-contract.md" in warns[0][2]


@pytest.mark.parametrize("attr, value", [
    ("style", "width: 10px; color: red"),
    ("style", "border-radius: 3px"),
    ("style", "background-image: url(/web/image/1)"),
    ("t-attf-style", "color: #{color}"),
    ("t-att-style", "'color: ' + color"),
    ("data-style", "color: #fff"),
])
def test_a_style_attribute_without_a_literal_colour_is_accepted(repo, capsys, attr, value):
    xml = _view(repo, f'<div {attr}="{value}">x</div>')
    assert _scheme(capsys, xml) == []


@pytest.mark.parametrize("cls", SCHEME_CLASSES)
@pytest.mark.parametrize("attr", ["class", "t-att-class", "t-attf-class"])
def test_a_class_that_fixes_a_scheme_warns(repo, capsys, attr, cls):
    """Fails if a scheme-fixing class is accepted in any of the three class attributes."""
    xml = _view(repo, f'<div {attr}="p-2 {cls} rounded">x</div>')
    warns = _by(_scheme(capsys, xml), "WARN")
    assert len(warns) == 1 and warns[0][1].endswith("v.xml:3")
    assert cls in warns[0][2]


@pytest.mark.parametrize("cls", [
    "bg-white-50", "text-bg-dark", "o_text_white_foo", "bg-view", "text-muted", "text-body",
    "bg-dark-subtle", "text-bg-light", "my-bg-white", "border-light-subtle",
])
def test_a_class_that_only_looks_like_a_scheme_class_is_accepted(repo, capsys, cls):
    """Fails if class matching is by substring instead of by whole class token."""
    xml = _view(repo, f'<div class="p-2 {cls} rounded">x</div>')
    assert _scheme(capsys, xml) == []


def test_a_class_list_wrapped_over_lines_is_judged_on_the_lines_that_were_added(repo, capsys):
    xml = _write(repo / "mine" / "views" / "v.xml", """\
        <odoo>
          <template id="t">
            <div class="p-2
                        bg-white">x</div>
            <p>keep</p>
          </template>
        </odoo>
    """)
    _sh(repo, "add", "-A")
    _sh(repo, "commit", "-q", "-m", "view")
    xml.write_text(xml.read_text(encoding="utf-8").replace("keep", "changed"), encoding="utf-8")
    assert _scheme(capsys, xml) == [], "the wrapped class was not added by this change"
    xml.write_text(xml.read_text(encoding="utf-8").replace("bg-white\"", "bg-white rounded\""),
                   encoding="utf-8")
    assert _lines(_by(_scheme(capsys, xml), "WARN")) == ["4"]


def test_scheme_findings_in_an_xml_comment_are_ignored(repo, capsys):
    xml = _write(repo / "mine" / "views" / "v.xml",
                 '<odoo>\n  <!-- <div class="bg-white" style="color: #fff"/> -->\n</odoo>\n')
    assert _scheme(capsys, xml) == []


@pytest.mark.parametrize("literal", ["'#fff'", '"#00BBCE"', "`rgb(1, 2, 3)`", "'rgba(0,0,0,.5)'",
                                     "'hsl(10, 20%, 30%)'"])
def test_a_literal_colour_in_a_js_string_warns(repo, capsys, literal):
    """Fails if a colour hard-coded in JavaScript is accepted."""
    js = _write(repo / "mine" / "static" / "src" / "chart.js",
                f"/** @odoo-module **/\nconst c = {literal};\n")
    warns = _by(_scheme(capsys, js), "WARN")
    assert len(warns) == 1 and warns[0][1].endswith("chart.js:2")
    assert "odoo-ui-contract.md" in warns[0][2]


def test_js_colours_in_comments_or_derived_from_values_are_not_findings(repo, capsys):
    js = _write(repo / "mine" / "static" / "src" / "chart.js", """\
        /** @odoo-module **/
        // const a = "#fff";
        /* const b = "rgb(0, 0, 0)";
           const c = '#000'; */
        const d = `rgb(${r}, ${g}, ${b})`;
        const e = getColor(3);
        const f = "#my-anchor";
        const g = "text-white";
    """)
    assert _scheme(capsys, js) == []


def test_the_core_pattern_passes_clean(repo, capsys):
    """Core's own shape: a light rule reading a component property with a core variable as
    fallback, a dark sheet holding only the override, and a manifest that removes the dark
    sheet from the light bundle and adds it to the dark one."""
    _module(repo, LIGHT_AND_DARK)
    light = _write(repo / "mymod" / "static" / "src" / "composer.scss",
                   ".o-mymod-Composer {\n"
                   "    background-color: var(--mymod-Composer-bg, $o-view-background-color);\n}\n")
    dark = _write(repo / "mymod" / "static" / "src" / "composer.dark.scss", DARK_SHEET)
    assert _scheme(capsys, light, dark) == []


# --- dark sheet registration ------------------------------------------------
def _dark(repo, assets=None, manifest=None):
    _module(repo, assets, manifest=manifest)
    return _write(repo / "mymod" / "static" / "src" / "sub" / "panel.dark.scss", DARK_SHEET)


def test_a_dark_sheet_missing_from_every_dark_bundle_blocks(repo, capsys):
    """Fails if a *.dark.scss that no *_dark bundle loads is accepted: it would never apply."""
    dark = _dark(repo, {"web.assets_backend": ["mymod/static/src/**/*.scss",
                                               ("remove", "mymod/static/src/**/*.dark.scss")]})
    blocks = _by(_scheme(capsys, dark), "BLOCK")
    assert len(blocks) == 1 and blocks[0][1].endswith("panel.dark.scss:1")
    assert "_dark" in blocks[0][2]


def test_a_dark_sheet_left_in_a_light_bundle_blocks(repo, capsys):
    """Fails if a *.dark.scss that a light bundle still globs in is accepted: it would repaint
    the light scheme."""
    dark = _dark(repo, {"web.assets_backend": ["mymod/static/src/**/*"],
                        "web.assets_web_dark": ["mymod/static/src/**/*.dark.scss"]})
    blocks = _by(_scheme(capsys, dark), "BLOCK")
    assert len(blocks) == 1 and blocks[0][1].endswith("panel.dark.scss:1")
    assert "web.assets_backend" in blocks[0][2]


def test_a_dark_sheet_taken_out_of_the_light_bundle_and_added_to_the_dark_one_passes(repo, capsys):
    dark = _dark(repo, LIGHT_AND_DARK)
    assert _scheme(capsys, dark) == []


@pytest.mark.parametrize("dark_entry", [
    "mymod/static/src/sub/panel.dark.scss",
    "mymod/static/src/sub/*.dark.scss",
    "mymod/static/src/**/*.dark.scss",
    "mymod/static/src/**",
])
def test_a_dark_sheet_registered_by_exact_path_or_glob_passes(repo, capsys, dark_entry):
    dark = _dark(repo, {"web.assets_web_dark": [dark_entry]})
    assert _scheme(capsys, dark) == []


def test_a_glob_that_does_not_cover_the_dark_sheet_does_not_register_it(repo, capsys):
    """`*` stays inside one directory; a glob for another folder covers nothing."""
    dark = _dark(repo, {"web.assets_web_dark": ["mymod/static/src/*.dark.scss",
                                                "other/static/src/**/*.dark.scss"]})
    assert len(_by(_scheme(capsys, dark), "BLOCK")) == 1


def test_a_remove_that_comes_before_the_include_does_not_take_the_sheet_out(repo, capsys):
    """Bundle entries apply in order: removing first and including after leaves it in."""
    dark = _dark(repo, {"web.assets_backend": [("remove", "mymod/static/src/**/*.dark.scss"),
                                               "mymod/static/src/**/*"],
                        "web.assets_web_dark": ["mymod/static/src/**/*.dark.scss"]})
    blocks = _by(_scheme(capsys, dark), "BLOCK")
    assert len(blocks) == 1 and "web.assets_backend" in blocks[0][2]


def test_a_remove_covering_the_sheet_by_a_wider_glob_takes_it_out(repo, capsys):
    dark = _dark(repo, {"web.assets_backend": ["mymod/static/src/**/*",
                                               ("remove", "mymod/**/*.dark.scss")],
                        "web.assets_web_dark": ["mymod/static/src/**/*.dark.scss"]})
    assert _scheme(capsys, dark) == []


def test_a_light_bundle_that_never_includes_the_sheet_is_not_a_finding(repo, capsys):
    dark = _dark(repo, {"web.assets_backend": ["mymod/static/src/js/**/*"],
                        "web.assets_tests": ["mymod/static/tests/**/*"],
                        "web.assets_web_dark": ["mymod/static/src/**/*.dark.scss"]})
    assert _scheme(capsys, dark) == []


def test_a_private_sub_bundle_is_left_to_the_bundle_that_includes_it(repo, capsys):
    """`web._assets_core` is only reached through an `include`; the includer owns the removal."""
    dark = _dark(repo, {"web._assets_core": ["mymod/static/src/**/*"],
                        "web.assets_web_dark": ["mymod/static/src/**/*.dark.scss"]})
    assert _scheme(capsys, dark) == []


def test_an_unreadable_manifest_warns_and_never_blocks(repo, capsys):
    dark = _dark(repo, manifest="{'name': 'm', 'assets': {'a': [os.path.join('x')]}}\n")
    found = _scheme(capsys, dark)
    assert _by(found, "BLOCK") == []
    warns = _by(found, "WARN")
    assert len(warns) == 1 and warns[0][1].endswith("panel.dark.scss:1")
    assert "manifest not readable" in warns[0][2]


def test_a_dark_sheet_outside_any_module_warns_and_never_blocks(tmp_path, capsys):
    dark = _write(tmp_path / "loose" / "panel.dark.scss", DARK_SHEET)
    found = _scheme(capsys, dark)
    assert _by(found, "BLOCK") == [] and len(_by(found, "WARN")) == 1


def _checkout_with_web(root, web_assets):
    _write(root / "odoo" / "release.py", "version_info = (19, 0, 0, 'final', 0, '')\n")
    _write(root / "addons" / "web" / "__manifest__.py",
           "{'name': 'web', 'assets': %r}\n" % (web_assets,))
    return root


WEB_WITH_DARK = {"web.assets_web_dark": [("include", "web.assets_web"),
                                         "web/static/src/**/*.dark.scss"]}


def test_a_series_without_a_dark_bundle_skips_registration_with_one_info_line(
        repo, tmp_path, capsys):
    """The registration check protects a bundle the series has; without one it is skipped,
    while the colour warnings still run."""
    root = _checkout_with_web(tmp_path / "odoo_old", {"web.assets_backend": ["web/static/src/**"]})
    dark = _dark(repo, {"web.assets_backend": ["mymod/static/src/**/*"]})
    other = _write(repo / "mymod" / "static" / "src" / "other.dark.scss", DARK_SHEET)
    css = _sheet(repo, ".o_panel {\n    color: #fff;\n}\n")
    found = _scheme(capsys, dark, other, css, odoo_root=str(root))
    assert _by(found, "BLOCK") == []
    assert len(_by(found, "INFO")) == 1
    assert _lines(_by(found, "WARN")) == ["2"]


def test_a_series_with_a_dark_bundle_checks_registration(repo, tmp_path, capsys):
    root = _checkout_with_web(tmp_path / "odoo_new", WEB_WITH_DARK)
    dark = _dark(repo, {"web.assets_backend": ["mymod/static/src/**/*"]})
    found = _scheme(capsys, dark, odoo_root=str(root))
    assert len(_by(found, "BLOCK")) == 2 and _by(found, "INFO") == []


def test_a_root_that_is_no_odoo_checkout_does_not_skip_registration(repo, tmp_path, capsys):
    dark = _dark(repo, {"web.assets_backend": ["mymod/static/src/**/*"]})
    found = _scheme(capsys, dark, odoo_root=str(tmp_path / "nowhere"))
    assert len(_by(found, "BLOCK")) == 2


def test_scheme_cli_prints_findings_and_exits_zero(repo):
    dark = _dark(repo, {"web.assets_backend": ["mymod/static/src/**/*"]})
    res = subprocess.run(
        [sys.executable, str(LIB), "scheme", "--base", "HEAD", str(dark)],
        capture_output=True, text=True, cwd=repo,
    )
    assert res.returncode == 0, res.stderr
    assert res.stdout.startswith("BLOCK|") and "panel.dark.scss:1|" in res.stdout
