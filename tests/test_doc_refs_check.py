"""scripts/lib/doc_refs_check.py - every rule catches its defect and lets the correct form pass.

A module's docs are published by an app store that serves the module's own files: an image path
pointing at the author's machine or a running instance, a link into a sibling checkout directory
(../../<other_module>/...), or a link pinned to one store host breaks once published. Each test
builds a small module in a temp dir, writes ONE reference, and runs the real CLI.
"""
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "doc_refs_check.py"
SERIES = "17.0"


@pytest.fixture
def module(tmp_path):
    mod = tmp_path / "addons" / "sale_delivery_window"
    for rel in ("static/description/banner.png", "static/description/img/form.png",
                "static/src/img/icon.png", "doc/shots/raw.png"):
        p = mod / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\x89PNG")
    (tmp_path / "addons" / "sale" / "static").mkdir(parents=True)
    (tmp_path / "addons" / "sale" / "static" / "x.png").write_bytes(b"\x89PNG")
    (mod / "__manifest__.py").write_text("{'name': 'X', 'images': ['static/description/banner.png']}\n")
    return mod


def _run(module, *files, series=SERIES):
    proc = subprocess.run([sys.executable, str(GATE), "--module-root", str(module),
                           "--series", series, *files], capture_output=True, text=True, timeout=30)
    return proc


def _rst(module, body):
    (module / "doc" / "index.rst").write_text(textwrap.dedent(body), encoding="utf-8")
    return _run(module, "doc/index.rst")


def _html(module, body):
    (module / "static" / "description" / "index.html").write_text(textwrap.dedent(body),
                                                                    encoding="utf-8")
    return _run(module, "static/description/index.html")


def _rules(proc):
    return [line.split(": ")[1] for line in proc.stdout.splitlines()]


def _clean(proc):
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout == ""


def _flags(proc, rule):
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert rule in _rules(proc), proc.stdout


# --------------------------------------------------------------------------- #
# images
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ref", [
    "https://cdn.example.com/a.png", "/static/description/banner.png",
    "file:///home/user/a.png", "http://localhost:8069/web/image/1", "localhost:8069/x.png",
    "http://127.0.0.1:8069/web/content/2",
])
def test_an_rst_image_that_is_not_relative_is_flagged(module, ref):
    _flags(_rst(module, f".. image:: {ref}\n"), "IMG_NOT_RELATIVE")


def test_a_relative_rst_image_under_static_passes(module):
    _clean(_rst(module, """\
        .. image:: ../static/description/img/form.png
           :width: 600

        .. figure:: ../static/src/img/icon.png

        .. |logo| image:: ../static/description/banner.png
        """))


def test_an_rst_image_escaping_the_module_is_flagged(module):
    _flags(_rst(module, ".. image:: ../../sale/static/x.png\n"), "IMG_ESCAPES_MODULE")


def test_a_missing_rst_image_is_flagged(module):
    _flags(_rst(module, ".. image:: ../static/description/img/nope.png\n"), "IMG_MISSING")


def test_an_rst_image_outside_static_is_not_served(module):
    _flags(_rst(module, ".. image:: shots/raw.png\n"), "IMG_NOT_SERVED")


def test_an_html_image_outside_static_description_is_not_served(module):
    _flags(_html(module, '<img src="../src/img/icon.png"/>\n'), "IMG_NOT_SERVED")


def test_html_images_inside_static_description_pass(module):
    _clean(_html(module, """\
        <section>
          <img src="img/form.png" class="img-fluid"/>
          <img srcset="banner.png 1x, img/form.png 2x"/>
          <div style="background-image: url('img/form.png')"></div>
        </section>
        """))


@pytest.mark.parametrize("markup,rule", [
    ('<img src="http://localhost:8069/web/image/res.partner/1/image_128"/>', "IMG_NOT_RELATIVE"),
    ('<img src="/sale_delivery_window/static/description/banner.png"/>', "IMG_NOT_RELATIVE"),
    ('<div style="background:url(/web/static/img/bg.png)"></div>', "IMG_NOT_RELATIVE"),
    ('<img srcset="img/missing.png 2x"/>', "IMG_MISSING"),
])
def test_html_image_defects_are_flagged(module, markup, rule):
    _flags(_html(module, markup), rule)


# --------------------------------------------------------------------------- #
# links
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ref", [
    "file:///home/user/odoo/doc.html", "http://localhost:8069/odoo/sales",
    "http://127.0.0.1:8069/web#action=1", "/home/user/addons/sale/README.rst",
    "/web#model=sale.order", "C:/Users/user/doc.html",
])
def test_a_local_link_is_flagged(module, ref):
    _flags(_rst(module, f"See `the page <{ref}>`_.\n"), "LINK_LOCAL")


def test_a_bare_local_url_in_text_is_flagged_but_not_inside_a_literal_block(module):
    _flags(_rst(module, "Open http://localhost:8069 in a browser.\n"), "LINK_LOCAL")
    _clean(_rst(module, """\
        Start the server::

            ./odoo-bin --http-port 8069 && open http://localhost:8069

        Or use ``http://localhost:8069`` directly.
        """))


def test_a_sibling_module_path_link_is_flagged(module):
    _flags(_rst(module, "Requires `Sales <../../sale/doc/index.rst>`_.\n"), "LINK_SIBLING_PATH")
    _flags(_html(module, '<a href="../../../sale/static/description/index.html">Sales</a>'),
           "LINK_SIBLING_PATH")


@pytest.mark.parametrize("ref", [
    "https://apps.odoo.com/apps/modules/17.0/sale",
    "https://apps.example.org/vi_VN/apps/modules/17.0/sale",
    "http://store.example.com/en/apps/modules/16.0/stock/",
])
def test_an_absolute_store_module_url_on_any_host_is_flagged(module, ref):
    _flags(_html(module, f'<a href="{ref}">x</a>'), "LINK_STORE_ABSOLUTE")


@pytest.mark.parametrize("ref", [
    "/apps/modules/16.0/sale",          # another series
    "/apps/modules/17.0/sale/",         # trailing slash
    "/vi_VN/apps/modules/17.0/sale",    # language prefix
    "/apps/modules/17.0/Sale-Module",   # not a technical name
    "/apps/modules/17.0",               # no module
])
def test_a_store_path_not_in_the_exact_scheme_is_flagged(module, ref):
    _flags(_rst(module, f"See `Sales <{ref}>`_.\n"), "LINK_STORE_SCHEME")


def test_the_store_module_scheme_for_this_series_passes(module):
    _clean(_rst(module, """\
        Requires `Sales <https://www.odoo.com/documentation/17.0/applications/sales.html>`_ and
        `Delivery </apps/modules/17.0/stock_delivery>`_.

        .. _store: /apps/modules/17.0/sale

        Contact `us <mailto:help@example.com>`_ or jump to `top <#top>`_.
        """))
    _clean(_html(module, '<a href="/apps/modules/17.0/sale">Sales</a> <a href="#features">x</a>'))


def test_anonymous_rst_links_and_targets_are_checked(module):
    """Cross-module links use the anonymous form (`text <url>`__): a repeated NAMED link makes
    docutils emit an INFO message that fails a report_level=1 gate."""
    _clean(_rst(module, """\
        Requires `sale </apps/modules/17.0/sale>`__ and `sale </apps/modules/17.0/sale>`__.

        .. __: /apps/modules/17.0/stock

        __ /apps/modules/17.0/account
        """))
    _flags(_rst(module, "`sale <../../sale/doc/index.rst>`__\n"), "LINK_SIBLING_PATH")
    _flags(_rst(module, ".. __: http://localhost:8069/odoo\n"), "LINK_LOCAL")
    _flags(_rst(module, "__ /apps/modules/16.0/sale\n"), "LINK_STORE_SCHEME")


def test_the_series_comes_from_the_caller(module):
    proc = _rst(module, "`Sales </apps/modules/18.0/sale>`_\n")
    _flags(proc, "LINK_STORE_SCHEME")
    _clean(_run(module, "doc/index.rst", series="18.0"))


def test_an_rst_image_target_option_is_checked_as_a_link(module):
    _flags(_rst(module, """\
        .. image:: ../static/description/banner.png
           :target: http://localhost:8069/odoo
        """), "LINK_LOCAL")


# --------------------------------------------------------------------------- #
# manifest
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("entry", [
    "/static/description/banner.png", "static/description/missing.png",
    "../sale/static/x.png", "https://cdn.example.com/banner.png",
])
def test_a_manifest_image_not_relative_or_missing_is_flagged(module, entry):
    (module / "__manifest__.py").write_text(
        "# comment\n{\n    'name': 'X',\n    'images': [\n        %r,\n    ],\n}\n" % entry)
    proc = _run(module, "__manifest__.py")
    _flags(proc, "MANIFEST_IMAGE")
    assert proc.stdout.startswith("__manifest__.py:5: MANIFEST_IMAGE:"), proc.stdout


def test_a_relative_existing_manifest_image_passes(module):
    _clean(_run(module, "__manifest__.py"))


# --------------------------------------------------------------------------- #
# CLI contract
# --------------------------------------------------------------------------- #
def test_default_files_cover_doc_description_readme_and_manifest(module):
    (module / "doc" / "index.rst").write_text(".. image:: ../static/description/nope.png\n")
    (module / "static" / "description" / "index.html").write_text('<a href="/web">x</a>')
    (module / "README.rst").write_text("`x <file:///tmp/a>`_\n")
    (module / "__manifest__.py").write_text("{'images': ['nope.png']}\n")
    proc = _run(module)
    assert proc.returncode == 1
    files = {line.split(":")[0] for line in proc.stdout.splitlines()}
    assert files == {"doc/index.rst", "static/description/index.html", "README.rst",
                     "__manifest__.py"}, proc.stdout


def test_output_is_file_line_rule_ref(module):
    proc = _rst(module, "Intro\n\n.. image:: /abs.png\n")
    assert proc.stdout == "doc/index.rst:3: IMG_NOT_RELATIVE: /abs.png\n"


@pytest.mark.parametrize("args", [
    ["--series", SERIES],                                         # no module root
    ["--module-root", "/nonexistent-module-root", "--series", SERIES],
    ["--module-root", "{mod}", "--series", "seventeen"],
    ["--module-root", "{mod}", "--series", SERIES, "doc/missing.rst"],
])
def test_usage_errors_exit_2(module, args):
    argv = [a.replace("{mod}", str(module)) for a in args]
    proc = subprocess.run([sys.executable, str(GATE), *argv], capture_output=True, text=True,
                          timeout=30)
    assert proc.returncode == 2, proc.stdout + proc.stderr


def test_an_interpreter_below_the_floor_exits_2_with_the_remedy():
    """Run under the version check alone: an old interpreter (an Odoo venv's) must be told to
    put the plugin's python3 first, not crash or pass."""
    src = GATE.read_text(encoding="utf-8")
    head = src.split("import argparse", 1)[0]
    code = ("import sys\n"
            "class V(tuple):\n    pass\n"
            "sys.version_info = V((3, 6, 9))\n" + head.split("import sys", 1)[1])
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          timeout=30, env=dict(os.environ, VIRTUAL_ENV="/opt/odoo-venv"))
    assert proc.returncode == 2
    assert "make python3 on PATH a Python >= 3.8 (deactivate the Odoo venv)" in proc.stderr


def test_the_gate_parses_on_python_3_8_grammar():
    import ast
    ast.parse(GATE.read_text(encoding="utf-8"), feature_version=(3, 8))
