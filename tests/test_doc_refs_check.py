"""scripts/lib/doc_refs_check.py - every rule catches its defect and lets the correct form pass.

A module's docs are published by an app store that serves the module's own files: an image path
pointing at the author's machine or a running instance, a link into a sibling checkout directory
(../../<other_module>/...), or a link pinned to one store host breaks once published. The stores
resolve a guide image only by its bare file name, looked up flat in static/description/, so every
shipped image lives there and the cover is the `*_screenshot` file the English page shows. An
image that is not a module file (a vendor logo) is a public https:// URL the stores keep as is.
Each test builds a small module in a temp dir, writes ONE reference, and runs the real CLI.
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
PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"


@pytest.fixture
def module(tmp_path):
    mod = tmp_path / "addons" / "sale_delivery_window"
    for rel in ("static/description/main_screenshot.png", "static/description/form.png",
                "static/description/img/form.png", "static/src/img/icon.png",
                "doc/shots/raw.png", "doc/raw.png"):
        p = mod / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(PNG)
    (tmp_path / "addons" / "sale" / "static").mkdir(parents=True)
    (tmp_path / "addons" / "sale" / "static" / "x.png").write_bytes(PNG)
    _manifest(mod, "static/description/main_screenshot.png")
    return mod


def _manifest(module, *images):
    (module / "__manifest__.py").write_text(
        "{'name': 'X', 'images': [%s]}\n" % ", ".join(repr(i) for i in images))


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
    "http://cdn.example.com/a.png", "//cdn.example.com/a.png", "/static/description/banner.png",
    "data:image/png;base64,iVBORw0KGgo=", "file:///home/user/a.png",
    "http://localhost:8069/web/image/1", "localhost:8069/x.png",
    "http://127.0.0.1:8069/web/content/2", "https://localhost/a.png", "https://127.0.0.2/a.png",
    "https://0.0.0.0/a.png", "https://[::1]/a.png", "https://192.168.1.5/a.png",
    "https://intranet/a.png",
])
def test_an_image_neither_a_module_path_nor_a_public_https_url_is_flagged(module, ref):
    _flags(_rst(module, f".. image:: {ref}\n"), "IMG_NOT_RELATIVE")
    _flags(_html(module, f'<img src="./main_screenshot.png"/><img src="{ref}"/>\n'),
           "IMG_NOT_RELATIVE")


@pytest.mark.parametrize("ref", [
    "https://raw.githubusercontent.com/acme/branding/0123abc/logo/acme-logo.svg",
    "https://cdn.example.com/brand/logo%20v2.png",
])
def test_a_public_https_image_is_not_a_module_file_and_passes(module, ref):
    """A vendor logo pinned to a public URL is displayed as is by the stores: no existence,
    flatness, name or orphan check applies to it."""
    _clean(_rst(module, f".. image:: {ref}\n"))
    _clean(_html(module, f'<img src="{ref}"/><img src="./main_screenshot.png"/>\n'))
    (module / "README.rst").write_text(f".. image:: {ref}\n")
    _clean(_run(module, "README.rst"))


@pytest.mark.parametrize("name", ["caf\u00e9.png", "shot(1).png", "a+b.png", "form,v2.png"])
def test_a_module_image_name_outside_the_safe_set_is_flagged(module, name):
    (module / "static" / "description" / name).write_bytes(PNG)
    _flags(_rst(module, f".. image:: {name}\n"), "IMG_NAME")
    _flags(_html(module, f'<img src="./main_screenshot.png"/><img src="./{name}"/>\n'), "IMG_NAME")
    _manifest(module, "static/description/main_screenshot.png", "static/description/" + name)
    _flags(_run(module, "__manifest__.py"), "IMG_NAME")


def test_an_html_image_whose_decoded_name_has_a_space_is_flagged(module):
    (module / "static" / "description" / "old one.png").write_bytes(PNG)
    _flags(_html(module, '<img src="./main_screenshot.png"/><img src="./old%20one.png"/>'),
           "IMG_NAME")


def test_a_module_image_name_in_the_safe_set_passes(module):
    (module / "static" / "description" / "Sales_Order-form.v2.png").write_bytes(PNG)
    _clean(_rst(module, ".. image:: Sales_Order-form.v2.png\n"))


def test_a_guide_image_named_bare_passes_in_every_directive(module):
    _clean(_rst(module, """\
        .. image:: form.png
           :width: 600

        .. figure:: main_screenshot.png

        .. |logo| image:: form.png
        """))


@pytest.mark.parametrize("directive", [
    ".. image:: {ref}", ".. figure:: {ref}", ".. |logo| image:: {ref}",
])
def test_every_rst_image_directive_is_checked(module, directive):
    """A figure or a substitution image is as much a published image as a plain one."""
    proc = _rst(module, directive.format(ref="../static/description/form.png") + "\n")
    assert _rules(proc) == ["IMG_NOT_BARE"], proc.stdout


@pytest.mark.parametrize("ref", [
    "../static/description/form.png", "shots/raw.png", "../../sale/static/x.png",
    "..\\static\\description\\form.png",
])
def test_a_guide_image_that_is_not_a_bare_name_is_flagged(module, ref):
    _flags(_rst(module, f".. image:: {ref}\n"), "IMG_NOT_BARE")


def test_a_bare_guide_image_absent_from_static_description_is_missing(module):
    proc = _rst(module, ".. image:: raw.png\n")
    assert proc.stdout == "doc/index.rst:1: IMG_MISSING: raw.png\n"
    assert proc.returncode == 1


@pytest.mark.parametrize("markup", [
    '<img src="img/form.png"/>', '<img src="../src/img/icon.png"/>',
])
def test_an_html_image_outside_static_description_is_not_flat(module, markup):
    _flags(_html(module, markup + "\n"), "IMG_NOT_FLAT")


@pytest.mark.parametrize("ref", [
    "../../../sale_delivery_window/static/description/form.png", "../description/form.png",
    "assets/../form.png", "./img/../form.png",
])
def test_an_html_image_resolving_flat_but_not_written_as_a_bare_file_is_not_flat(module, ref):
    """Odoo rewrites only a src with no `//` and no `static/`; any directory part breaks there."""
    proc = _html(module, f'<img src="./main_screenshot.png"/><img src="{ref}"/>\n')
    assert _rules(proc) == ["IMG_NOT_FLAT"], proc.stdout


def test_an_html_image_escaping_the_module_is_flagged(module):
    _flags(_html(module, '<img src="../../../sale/static/x.png"/>\n'), "IMG_ESCAPES_MODULE")


def test_a_readme_image_names_its_static_description_path(module):
    (module / "README.rst").write_text(".. image:: static/description/form.png\n")
    _clean(_run(module, "README.rst"))
    (module / "README.rst").write_text(".. image:: static/description/img/form.png\n")
    _flags(_run(module, "README.rst"), "IMG_NOT_FLAT")


def test_html_images_flat_in_static_description_pass(module):
    _clean(_html(module, """\
        <section>
          <img src="./main_screenshot.png" class="img-fluid"/>
          <img srcset="form.png 1x, ./main_screenshot.png 2x"/>
          <div style="background-image: url('./form.png')"></div>
        </section>
        """))


@pytest.mark.parametrize("markup,rule", [
    ('<img src="http://localhost:8069/web/image/res.partner/1/image_128"/>', "IMG_NOT_RELATIVE"),
    ('<img src="/sale_delivery_window/static/description/banner.png"/>', "IMG_NOT_RELATIVE"),
    ('<div style="background:url(/web/static/img/bg.png)"></div>', "IMG_NOT_RELATIVE"),
    ('<img srcset="./missing.png 2x"/>', "IMG_MISSING"),
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
    _clean(_html(module, '<img src="./main_screenshot.png"/>'
                         '<a href="/apps/modules/17.0/sale">Sales</a> <a href="#features">x</a>'))


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
        .. image:: form.png
           :target: http://localhost:8069/odoo
        """), "LINK_LOCAL")


# --------------------------------------------------------------------------- #
# manifest
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("entry", [
    "/static/description/main_screenshot.png", "static/description/missing_screenshot.png",
    "../sale/static/x.png", "https://cdn.example.com/main_screenshot.png",
    "static/description/img/form.png", "static/src/img/icon.png", "doc/raw.png",
    "static/description/notes_screenshot.txt",
])
def test_a_manifest_image_not_an_existing_static_description_image_is_flagged(module, entry):
    if entry.endswith(".txt"):
        (module / entry).write_text("x")
    (module / "__manifest__.py").write_text(
        "# comment\n{\n    'name': 'X',\n    'images': [\n        %r,\n    ],\n}\n" % entry)
    proc = _run(module, "__manifest__.py")
    _flags(proc, "MANIFEST_IMAGE")
    assert proc.stdout.startswith("__manifest__.py:5: MANIFEST_IMAGE:"), proc.stdout


@pytest.mark.parametrize("cover", [
    "main_screenshot.png", "banner_screenshot.jpg", "main_screenshot.gif", "hero_screenshot.jpeg",
])
def test_a_screenshot_named_cover_passes(module, cover):
    (module / "static" / "description" / cover).write_bytes(PNG)
    _manifest(module, "static/description/" + cover, "static/description/form.png")
    _clean(_run(module, "__manifest__.py"))


@pytest.mark.parametrize("cover", ["form.png", "main_screenshot.vi_VN.png", "screenshot.png"])
def test_a_cover_not_named_screenshot_is_flagged(module, cover):
    (module / "static" / "description" / cover).write_bytes(PNG)
    _manifest(module, "static/description/" + cover, "static/description/main_screenshot.png")
    proc = _run(module, "__manifest__.py")
    assert _rules(proc) == ["MANIFEST_COVER"], proc.stdout
    assert proc.returncode == 1


# --------------------------------------------------------------------------- #
# cover shown on the English store page
# --------------------------------------------------------------------------- #
def test_an_english_page_not_showing_the_cover_is_flagged(module):
    proc = _html(module, '<p>x</p>\n<img src="./form.png"/>\n')
    assert proc.stdout == ("static/description/index.html:0: IMG_COVER_NOT_SHOWN: "
                           "static/description/main_screenshot.png\n")
    assert proc.returncode == 1


def test_an_english_page_with_no_image_does_not_show_the_cover(module):
    _flags(_html(module, '<section><h1>Title</h1></section>'), "IMG_COVER_NOT_SHOWN")


@pytest.mark.parametrize("markup", [
    '<img src="./form.png"/><img src="./main_screenshot.png"/>',
    '<img src="https://raw.githubusercontent.com/acme/brand/0123abc/logo.png"/>'
    '<img src="./main_screenshot.png"/>',
    '<img srcset="./form.png 1x, main_screenshot.png 2x"/>',
    '<div style="background:url(./main_screenshot.png)"></div>',
])
def test_the_cover_may_appear_anywhere_after_a_logo_or_another_image(module, markup):
    """The template places the cover in the HERO; a vendor logo, external or local, may come
    first."""
    _clean(_html(module, markup))


def test_a_cover_reference_resolving_elsewhere_does_not_show_the_cover(module):
    (module / "static" / "description" / "img" / "main_screenshot.png").write_bytes(PNG)
    _flags(_html(module, '<img src="./img/main_screenshot.png"/>'), "IMG_COVER_NOT_SHOWN")


def test_a_localized_page_is_not_held_to_the_english_cover(module):
    page = module / "static" / "description" / "index_vi_VN.html"
    page.write_text('<img src="./form.png"/>\n', encoding="utf-8")
    _clean(_run(module, "static/description/index_vi_VN.html"))


def test_a_page_is_not_held_to_a_cover_the_manifest_does_not_declare(module):
    _manifest(module)
    _clean(_html(module, '<section><img src="./form.png"/></section>'))


# --------------------------------------------------------------------------- #
# orphans (whole-module mode)
# --------------------------------------------------------------------------- #
@pytest.fixture
def shipped(module):
    """A module whose every image is referenced: the whole-module run is clean."""
    for rel in ("static/description/img/form.png", "static/src/img/icon.png",
                "doc/shots/raw.png", "doc/raw.png"):
        (module / rel).unlink()
    (module / "doc" / "index.rst").write_text(".. image:: form.png\n")
    (module / "static" / "description" / "index.html").write_text(
        '<img src="./main_screenshot.png"/>\n')
    _clean(_run(module))
    return module


def test_an_image_nothing_references_is_an_orphan(shipped):
    (shipped / "static" / "description" / "old.png").write_bytes(PNG)
    (shipped / "doc" / "images").mkdir()
    (shipped / "doc" / "images" / "stale.gif").write_bytes(PNG)
    proc = _run(shipped)
    assert proc.stdout == ("doc/images/stale.gif:0: IMG_ORPHAN: doc/images/stale.gif\n"
                           "static/description/old.png:0: IMG_ORPHAN: static/description/old.png\n")
    assert proc.returncode == 1


@pytest.mark.parametrize("rel,text,name", [
    ("views/res_config_views.xml",
     '<img src="/sale_delivery_window/static/description/old.png"/>', "old.png"),
    ("i18n/vi.po", 'msgid "See old.png"\nmsgstr ""\n', "old.png"),
    ("static/description/index_vi_VN.html", '<img src="./old%20one.png"/>', "old one.png"),
])
def test_an_image_referenced_by_any_other_text_file_is_not_an_orphan(shipped, rel, text, name):
    (shipped / "static" / "description" / name).write_bytes(PNG)
    (shipped / rel).parent.mkdir(parents=True, exist_ok=True)
    (shipped / rel).write_text(text)
    assert "IMG_ORPHAN" not in _rules(_run(shipped))


def test_the_module_icon_is_never_an_orphan(shipped):
    (shipped / "static" / "description" / "icon.png").write_bytes(PNG)
    (shipped / "static" / "description" / "icon.svg").write_text("<svg/>")
    _clean(_run(shipped))


@pytest.mark.parametrize("mention", [
    "See old.png.", "(old.png)", "old.png, then", '"old.png"', "see old.png;", "old.png:",
])
def test_a_mention_followed_by_punctuation_references_the_image(shipped, mention):
    (shipped / "static" / "description" / "old.png").write_bytes(PNG)
    (shipped / "README.rst").write_text(mention + "\n")
    assert "IMG_ORPHAN" not in _rules(_run(shipped)), mention


@pytest.mark.parametrize("rel", [".git/COMMIT_EDITMSG", "__pycache__/notes.txt"])
def test_a_mention_in_a_vcs_or_cache_directory_is_not_a_reference(shipped, rel):
    (shipped / "static" / "description" / "old.png").write_bytes(PNG)
    (shipped / rel).parent.mkdir(parents=True, exist_ok=True)
    (shipped / rel).write_text("drop old.png from the landing\n")
    assert "static/description/old.png:0: IMG_ORPHAN: static/description/old.png" in \
        _run(shipped).stdout


def test_a_mention_inside_a_binary_file_is_not_a_reference(shipped):
    (shipped / "static" / "description" / "old.png").write_bytes(PNG)
    (shipped / "static" / "src" / "fonts").mkdir(parents=True)
    (shipped / "static" / "src" / "fonts" / "brand.woff").write_bytes(b"wOFF\0\0 old.png \0")
    assert "static/description/old.png:0: IMG_ORPHAN: static/description/old.png" in \
        _run(shipped).stdout


def test_a_longer_name_containing_the_file_name_does_not_reference_it(shipped):
    (shipped / "static" / "description" / "old.png").write_bytes(PNG)
    (shipped / "README.rst").write_text("See myold.png and old.png.bak\n")
    assert "IMG_ORPHAN" in _rules(_run(shipped))


def test_orphans_are_not_reported_when_files_are_named(shipped):
    (shipped / "static" / "description" / "old.png").write_bytes(PNG)
    _clean(_run(shipped, "doc/index.rst"))


# --------------------------------------------------------------------------- #
# CLI contract
# --------------------------------------------------------------------------- #
def test_default_files_cover_doc_description_readme_and_manifest(module):
    (module / "doc" / "index.rst").write_text(".. image:: nope.png\n")
    (module / "static" / "description" / "index.html").write_text('<a href="/web">x</a>')
    (module / "README.rst").write_text("`x <file:///tmp/a>`_\n")
    (module / "__manifest__.py").write_text("{'images': ['nope.png']}\n")
    proc = _run(module)
    assert proc.returncode == 1
    files = {line.split(":")[0] for line in proc.stdout.splitlines()}
    assert {"doc/index.rst", "static/description/index.html", "README.rst",
            "__manifest__.py"} <= files, proc.stdout


def test_output_is_file_line_rule_ref(module):
    proc = _rst(module, "Intro\n\n.. image:: /abs.png\n")
    assert proc.stdout == "doc/index.rst:3: IMG_NOT_RELATIVE: /abs.png\n"


def test_help_exits_0_and_prints_the_usage():
    proc = subprocess.run([sys.executable, str(GATE), "--help"], capture_output=True, text=True,
                          timeout=30)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "--module-root" in proc.stdout


@pytest.mark.parametrize("args", [
    ["--series", SERIES],                                         # no module root
    ["--module-root", "{mod}", "--series", SERIES, "--bogus"],    # unknown flag
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
