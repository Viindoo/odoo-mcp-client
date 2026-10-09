"""scripts/lib/doc_refs_check.py - every rule catches its defect and lets the correct form pass.

A module's docs are published by an app store that serves the module's own files: an image path
pointing at the author's machine or a running instance, a link into a sibling checkout directory
(../../<other_module>/...), or a link pinned to one store host breaks once published. The stores
and Odoo's own Apps view rewrite a relative image path in a guide or a store page against the
module's static/description/, subfolders included, and leave `../static/description/<file>`
unrewritten. So the root of static/description/ holds only the icon, the pages and the cover
(`main_screenshot`, the file the English page shows), and every other shipped image lives
directly in static/description/assets/. An image that is not a module file (a vendor logo) is a
public https:// URL the stores keep as is.
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
# Every off-convention location below holds a real file, so a finding is about the form alone.
STRAY = ("static/description/form.png", "static/description/assets/sub/form.png",
         "static/description/img/form.png", "static/src/img/icon.png", "doc/shots/raw.png",
         "doc/raw.png")


@pytest.fixture
def module(tmp_path):
    mod = tmp_path / "addons" / "sale_delivery_window"
    for rel in ("static/description/main_screenshot.png",
                "static/description/assets/form.png") + STRAY:
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


def _readme(module, ref):
    (module / "README.rst").write_text(".. image:: %s\n" % ref)
    return _run(module, "README.rst")


def _rules(proc):
    return [line.split(": ")[1] for line in proc.stdout.splitlines()]


def _clean(proc):
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout == ""


def _flags(proc, rule):
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert rule in _rules(proc), proc.stdout


def _only(proc, rule):
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert _rules(proc) == [rule], proc.stdout


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
    # a reserved or private-use name, equal to it or under it
    "https://shop.localhost/a.png", "https://odoo.local/a.png", "https://erp.internal/a.png",
    "https://nas.lan/a.png", "https://router.home.arpa/a.png", "https://docs.test/a.png",
    "https://logo.invalid/a.png", "https://brand.example/a.png",
    "https://localhost.localdomain/a.png", "https://odoo.local./a.png",
    # an Odoo instance route on a public host
    "https://erp.acme.com/web/image/res.partner/1/image_128",
    "https://erp.acme.com/web/image?model=res.company&id=1&field=logo",
    "https://erp.acme.com/web/content/42", "https://erp.acme.com/web/binary/company_logo",
])
def test_an_image_on_a_reserved_host_or_an_instance_route_is_not_public(module, ref):
    """A reserved name never resolves for a store reader, and an instance route points at a
    running Odoo that the reader cannot reach."""
    _flags(_rst(module, f".. image:: {ref}\n"), "IMG_NOT_RELATIVE")
    _flags(_html(module, f'<img src="./main_screenshot.png"/><img src="{ref}"/>\n'),
           "IMG_NOT_RELATIVE")


@pytest.mark.parametrize("ref", [
    "https://example.com/logo.png", "https://cdn.testing.com/a.png",
    "https://cdn.acme.com/web/images/logo.png", "https://cdn.acme.com/brand/odoo/logo.png",
    # a file in the odoo/odoo repository, not a running instance
    "https://raw.githubusercontent.com/odoo/odoo/0123abc/addons/web/static/img/logo.png",
])
def test_a_public_name_merely_resembling_a_reserved_one_passes(module, ref):
    _clean(_rst(module, f".. image:: {ref}\n"))


@pytest.mark.parametrize("ref", [
    "https://raw.githubusercontent.com/acme/branding/0123abc/logo/acme-logo.svg",
    "https://cdn.example.com/brand/logo%20v2.png",
])
def test_a_public_https_image_passes_pinned_or_not(module, ref):
    """A vendor logo at a public URL is displayed as is by the stores: no existence, location,
    name or orphan check applies, and the gate does not check pinning (the second URL is not
    pinned to a revision)."""
    _clean(_rst(module, f".. image:: {ref}\n"))
    _clean(_html(module, f'<img src="{ref}"/><img src="./main_screenshot.png"/>\n'))
    _clean(_readme(module, ref))


@pytest.mark.parametrize("name", ["caf\u00e9.png", "shot(1).png", "a+b.png", "form,v2.png"])
def test_a_module_image_name_outside_the_safe_set_is_flagged(module, name):
    (module / "static" / "description" / "assets" / name).write_bytes(PNG)
    _only(_rst(module, f".. image:: assets/{name}\n"), "IMG_NAME")
    _only(_html(module, f'<img src="./main_screenshot.png"/><img src="./assets/{name}"/>\n'),
          "IMG_NAME")
    _manifest(module, "static/description/main_screenshot.png",
              "static/description/assets/" + name)
    _only(_run(module, "__manifest__.py"), "IMG_NAME")


def test_an_html_image_whose_decoded_name_has_a_space_is_flagged(module):
    (module / "static" / "description" / "assets" / "old one.png").write_bytes(PNG)
    _only(_html(module, '<img src="./main_screenshot.png"/><img src="./assets/old%20one.png"/>'),
          "IMG_NAME")


def test_a_module_image_name_in_the_safe_set_passes(module):
    (module / "static" / "description" / "assets" / "Sales_Order-form.v2.png").write_bytes(PNG)
    _clean(_rst(module, ".. image:: assets/Sales_Order-form.v2.png\n"))


def test_a_guide_image_in_assets_or_the_root_cover_passes_in_every_directive(module):
    (module / "static" / "description" / "main_screenshot.vi_VN.png").write_bytes(PNG)
    _clean(_rst(module, """\
        .. image:: assets/form.png
           :width: 600

        .. figure:: main_screenshot.png

        .. |logo| image:: assets/form.png

        .. image:: main_screenshot.vi_VN.png
        """))


@pytest.mark.parametrize("directive", [
    ".. image:: {ref}", ".. figure:: {ref}", ".. |logo| image:: {ref}",
])
def test_every_rst_image_directive_is_checked(module, directive):
    """A figure or a substitution image is as much a published image as a plain one."""
    proc = _rst(module, directive.format(ref="../static/description/assets/form.png") + "\n")
    assert _rules(proc) == ["IMG_NOT_IN_ASSETS"], proc.stdout


@pytest.mark.parametrize("ref", [
    "form.png",                                  # a screenshot left at the root
    "../static/description/assets/form.png",     # the store leaves this unrewritten
    "../static/description/main_screenshot.png",
    "assets/sub/form.png", "img/form.png", "shots/raw.png", "doc/raw.png",
    "./assets/form.png", "static/description/assets/form.png", "../../sale/static/x.png",
    "..\\static\\description\\assets\\form.png", "assets\\form.png",
])
def test_a_guide_image_not_in_assets_is_flagged(module, ref):
    _only(_rst(module, f".. image:: {ref}\n"), "IMG_NOT_IN_ASSETS")


@pytest.mark.parametrize("ref", ["assets/raw.png", "main_screenshot.vi_VN.png"])
def test_a_guide_image_in_its_form_but_absent_from_static_description_is_missing(module, ref):
    proc = _rst(module, f".. image:: {ref}\n")
    assert proc.stdout == f"doc/index.rst:1: IMG_MISSING: {ref}\n"
    assert proc.returncode == 1


@pytest.mark.parametrize("ref", [
    "./form.png", "form.png",                    # a screenshot left at the root
    "img/form.png", "./assets/sub/form.png", "../src/img/icon.png",
    "../description/assets/form.png", "assets/../assets/form.png", "./img/../assets/form.png",
    "../../../sale_delivery_window/static/description/assets/form.png",
])
def test_an_html_image_not_written_as_assets_or_the_cover_is_flagged(module, ref):
    """Odoo rewrites only a src with no `//` and no `static/`, and the stores rewrite the same
    relative form; a path reaching the file another way breaks on one of them."""
    _only(_html(module, f'<img src="./main_screenshot.png"/><img src="{ref}"/>\n'),
          "IMG_NOT_IN_ASSETS")


def test_an_html_image_escaping_the_module_is_flagged(module):
    _flags(_html(module, '<img src="../../../sale/static/x.png"/>\n'), "IMG_ESCAPES_MODULE")


@pytest.mark.parametrize("ref", [
    "static/description/assets/form.png", "./static/description/assets/form.png",
    "static/description/main_screenshot.png",
])
def test_a_readme_image_names_its_static_description_assets_path(module, ref):
    _clean(_readme(module, ref))


@pytest.mark.parametrize("ref", [
    "static/description/form.png", "static/description/img/form.png",
    "static/description/assets/sub/form.png", "assets/form.png", "static/src/img/icon.png",
])
def test_a_readme_image_not_in_assets_is_flagged(module, ref):
    _only(_readme(module, ref), "IMG_NOT_IN_ASSETS")


def test_html_images_in_assets_or_the_cover_pass(module):
    _clean(_html(module, """\
        <section>
          <img src="./main_screenshot.png" class="img-fluid"/>
          <img src="main_screenshot.png"/>
          <img src="assets/form.png"/>
          <img srcset="./assets/form.png 1x, ./main_screenshot.png 2x"/>
          <div style="background-image: url('./assets/form.png')"></div>
        </section>
        """))


@pytest.mark.parametrize("markup,rule", [
    ('<img src="http://localhost:8069/web/image/res.partner/1/image_128"/>', "IMG_NOT_RELATIVE"),
    ('<img src="/sale_delivery_window/static/description/banner.png"/>', "IMG_NOT_RELATIVE"),
    ('<div style="background:url(/web/static/img/bg.png)"></div>', "IMG_NOT_RELATIVE"),
    ('<img srcset="./assets/missing.png 2x"/>', "IMG_MISSING"),
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


@pytest.mark.parametrize("ref", [
    "https://erp.local/odoo/sales", "https://shop.localhost/", "https://erp.internal/web",
    "https://nas.lan/doc", "https://router.home.arpa/", "https://docs.test/guide",
    "https://logo.invalid/", "https://brand.example/", "http://localhost.localdomain:8069/odoo",
    "https://erp.local./odoo",
])
def test_a_link_to_a_reserved_or_private_use_name_is_local(module, ref):
    """A reserved name never resolves for a store reader, exactly as for an image."""
    _flags(_rst(module, f"See `the page <{ref}>`_.\n"), "LINK_LOCAL")
    _flags(_rst(module, f"Open {ref} in a browser.\n"), "LINK_LOCAL")
    _flags(_html(module, f'<img src="./main_screenshot.png"/><a href="{ref}">x</a>'), "LINK_LOCAL")


@pytest.mark.parametrize("ref", [
    "https://example.com/docs", "https://www.testing.com/", "https://shop.localhost.com/",
])
def test_a_link_to_a_public_name_resembling_a_reserved_one_passes(module, ref):
    _clean(_rst(module, f"See `the page <{ref}>`_.\n"))


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


def test_the_root_relative_vendor_listing_passes(module):
    """/apps/modules/browse?author=<vendor> resolves on every store that serves the module."""
    _clean(_rst(module, """\
        More from `Acme </apps/modules/browse?author=Acme%20Ltd>`__.

        .. __: /apps/modules/browse?author=Acme
        """))
    _clean(_html(module, '<img src="./main_screenshot.png"/>'
                         '<a href="/apps/modules/browse?author=Acme&amp;series=17.0">Acme</a>'))


@pytest.mark.parametrize("ref,rule", [
    ("https://apps.odoo.com/apps/modules/browse?author=Acme", "LINK_STORE_ABSOLUTE"),
    ("https://store.example.org/vi_VN/apps/modules/browse?author=Acme", "LINK_STORE_ABSOLUTE"),
    ("/vi_VN/apps/modules/browse?author=Acme", "LINK_STORE_SCHEME"),
    ("/en/apps/modules/browse?author=Acme", "LINK_STORE_SCHEME"),
    ("/apps/modules/browse", "LINK_STORE_SCHEME"),
    ("/apps/modules/browse?author=", "LINK_STORE_SCHEME"),
    ("/apps/modules/browse?search=Acme", "LINK_STORE_SCHEME"),
    ("/apps/modules/browse/?author=Acme", "LINK_STORE_SCHEME"),
])
def test_a_vendor_listing_not_in_the_root_relative_form_is_flagged(module, ref, rule):
    _flags(_html(module, f'<img src="./main_screenshot.png"/><a href="{ref}">Acme</a>'), rule)


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
        .. image:: assets/form.png
           :target: http://localhost:8069/odoo
        """), "LINK_LOCAL")


# --------------------------------------------------------------------------- #
# manifest
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("entry", [
    "/static/description/assets/form.png", "static/description/assets/missing.png",
    "static/description/form.png",               # a screenshot left at the root
    "static/description/assets/sub/form.png", "static/description/img/form.png",
    "../sale/static/x.png", "https://cdn.example.com/form.png", "static/src/img/icon.png",
    "doc/raw.png", "static/description/assets/notes.txt",
])
def test_a_manifest_image_not_an_existing_assets_image_or_the_cover_is_flagged(module, entry):
    if entry.endswith(".txt"):
        (module / entry).write_text("x")
    (module / "__manifest__.py").write_text(
        "# comment\n{\n    'name': 'X',\n    'images': [\n"
        "        'static/description/main_screenshot.png',\n        %r,\n    ],\n}\n" % entry)
    proc = _run(module, "__manifest__.py")
    assert proc.stdout == "__manifest__.py:6: MANIFEST_IMAGE: %s\n" % entry
    assert proc.returncode == 1


@pytest.mark.parametrize("cover", [
    "main_screenshot.png", "main_screenshot.gif", "main_screenshot.jpeg", "main_screenshot.jpg",
])
def test_the_main_screenshot_cover_with_assets_and_locale_covers_after_it_passes(module, cover):
    for name in (cover, "main_screenshot.vi_VN.png"):
        (module / "static" / "description" / name).write_bytes(PNG)
    _manifest(module, "static/description/" + cover, "static/description/assets/form.png",
              "static/description/main_screenshot.vi_VN.png")
    _clean(_run(module, "__manifest__.py"))


@pytest.mark.parametrize("cover", [
    "static/description/assets/form.png", "static/description/main_screenshot.vi_VN.png",
    "static/description/assets/main_screenshot.png",
])
def test_a_first_image_that_is_not_the_root_main_screenshot_is_not_the_cover(module, cover):
    for rel in (cover, "static/description/assets/main_screenshot.png"):
        (module / rel).write_bytes(PNG)
    _manifest(module, cover, "static/description/main_screenshot.png")
    _only(_run(module, "__manifest__.py"), "MANIFEST_COVER")


def test_another_screenshot_named_image_at_the_root_is_neither_the_cover_nor_in_assets(module):
    (module / "static" / "description" / "banner_screenshot.jpg").write_bytes(PNG)
    _manifest(module, "static/description/banner_screenshot.jpg")
    assert _rules(_run(module, "__manifest__.py")) == ["MANIFEST_IMAGE", "MANIFEST_COVER"]


# --------------------------------------------------------------------------- #
# cover shown on the English store page
# --------------------------------------------------------------------------- #
def test_an_english_page_not_showing_the_cover_is_flagged(module):
    proc = _html(module, '<p>x</p>\n<img src="./assets/form.png"/>\n')
    assert proc.stdout == ("static/description/index.html:0: IMG_COVER_NOT_SHOWN: "
                           "static/description/main_screenshot.png\n")
    assert proc.returncode == 1


def test_an_english_page_with_no_image_does_not_show_the_cover(module):
    _flags(_html(module, '<section><h1>Title</h1></section>'), "IMG_COVER_NOT_SHOWN")


@pytest.mark.parametrize("markup", [
    '<img src="./assets/form.png"/><img src="./main_screenshot.png"/>',
    '<img src="https://raw.githubusercontent.com/acme/brand/0123abc/logo.png"/>'
    '<img src="./main_screenshot.png"/>',
    '<img srcset="./assets/form.png 1x, main_screenshot.png 2x"/>',
    '<div style="background:url(./main_screenshot.png)"></div>',
])
def test_the_cover_may_appear_anywhere_after_a_logo_or_another_image(module, markup):
    """The template places the cover in the HERO; a vendor logo, external or local, may come
    first."""
    _clean(_html(module, markup))


@pytest.mark.parametrize("ref", ["./img/main_screenshot.png", "./assets/main_screenshot.png"])
def test_a_cover_reference_resolving_elsewhere_does_not_show_the_cover(module, ref):
    for sub in ("img", "assets"):
        (module / "static" / "description" / sub / "main_screenshot.png").write_bytes(PNG)
    _flags(_html(module, f'<img src="{ref}"/>'), "IMG_COVER_NOT_SHOWN")


def test_a_localized_page_is_not_held_to_the_english_cover(module):
    page = module / "static" / "description" / "index_vi_VN.html"
    page.write_text('<img src="./assets/form.png"/>\n', encoding="utf-8")
    _clean(_run(module, "static/description/index_vi_VN.html"))


def test_a_page_is_not_held_to_a_cover_the_manifest_does_not_declare(module):
    _manifest(module)
    _clean(_html(module, '<section><img src="./assets/form.png"/></section>'))


# --------------------------------------------------------------------------- #
# orphans (whole-module mode)
# --------------------------------------------------------------------------- #
OLD = "static/description/assets/old.png"


@pytest.fixture
def shipped(module):
    """A module whose every image is referenced: the whole-module run is clean."""
    for rel in STRAY:
        (module / rel).unlink()
    (module / "doc" / "index.rst").write_text(".. image:: assets/form.png\n")
    (module / "static" / "description" / "index.html").write_text(
        '<img src="./main_screenshot.png"/>\n')
    _clean(_run(module))
    return module


def test_an_image_nothing_references_is_an_orphan(shipped):
    """In assets/, left at the root of static/description/, or under doc/ - each is reported."""
    (shipped / OLD).write_bytes(PNG)
    (shipped / "static" / "description" / "stray.png").write_bytes(PNG)
    (shipped / "doc" / "images").mkdir()
    (shipped / "doc" / "images" / "stale.gif").write_bytes(PNG)
    proc = _run(shipped)
    assert proc.stdout == ("doc/images/stale.gif:0: IMG_ORPHAN: doc/images/stale.gif\n"
                           f"{OLD}:0: IMG_ORPHAN: {OLD}\n"
                           "static/description/stray.png:0: IMG_ORPHAN: "
                           "static/description/stray.png\n")
    assert proc.returncode == 1


@pytest.mark.parametrize("rel,text,name", [
    ("views/res_config_views.xml",
     '<img src="/sale_delivery_window/static/description/assets/old.png"/>', "old.png"),
    ("i18n/vi.po", 'msgid "See old.png"\nmsgstr ""\n', "old.png"),
    ("static/description/index_vi_VN.html", '<img src="./assets/old%20one.png"/>', "old one.png"),
])
def test_an_image_referenced_by_any_other_text_file_is_not_an_orphan(shipped, rel, text, name):
    (shipped / "static" / "description" / "assets" / name).write_bytes(PNG)
    (shipped / rel).parent.mkdir(parents=True, exist_ok=True)
    (shipped / rel).write_text(text)
    assert "IMG_ORPHAN" not in _rules(_run(shipped))


def test_a_root_copy_of_an_assets_image_referenced_only_through_assets_is_an_orphan(shipped):
    """A screenshot copied into assets/ while an old reference still pointed at the root keeps its
    root copy alive only while something still names that copy."""
    (shipped / "static" / "description" / "form.png").write_bytes(PNG)
    proc = _run(shipped)
    assert proc.stdout == ("static/description/form.png:0: IMG_ORPHAN: "
                           "static/description/form.png\n")
    (shipped / "doc" / "index_vi_VN.rst").write_text(
        ".. image:: assets/form.png\n\n.. image:: ../static/description/form.png\n")
    assert "IMG_ORPHAN" not in _rules(_run(shipped))


@pytest.mark.parametrize("mention", [
    "./assets/old.png", "../assets/old.png", "assets/old.png", "old.png",
    "/sale_delivery_window/static/description/assets/old.png",
])
def test_a_mention_bare_or_through_the_images_own_directory_references_it(shipped, mention):
    (shipped / OLD).write_bytes(PNG)
    (shipped / "views" / "x.xml").parent.mkdir(parents=True, exist_ok=True)
    (shipped / "views" / "x.xml").write_text(f'<img src="{mention}"/>\n')
    assert "IMG_ORPHAN" not in _rules(_run(shipped)), mention


@pytest.mark.parametrize("mention", ["img/old.png", "static/description/old.png"])
def test_a_mention_through_another_directory_does_not_reference_the_image(shipped, mention):
    (shipped / OLD).write_bytes(PNG)
    (shipped / "README.rst").write_text(mention + "\n")
    assert f"{OLD}:0: IMG_ORPHAN: {OLD}" in _run(shipped).stdout, mention


def test_the_module_icon_is_never_an_orphan(shipped):
    (shipped / "static" / "description" / "icon.png").write_bytes(PNG)
    (shipped / "static" / "description" / "icon.svg").write_text("<svg/>")
    _clean(_run(shipped))


@pytest.mark.parametrize("mention", [
    "See old.png.", "(old.png)", "old.png, then", '"old.png"', "see old.png;", "old.png:",
])
def test_a_mention_followed_by_punctuation_references_the_image(shipped, mention):
    (shipped / OLD).write_bytes(PNG)
    (shipped / "README.rst").write_text(mention + "\n")
    assert "IMG_ORPHAN" not in _rules(_run(shipped)), mention


@pytest.mark.parametrize("rel", [".git/COMMIT_EDITMSG", "__pycache__/notes.txt"])
def test_a_mention_in_a_vcs_or_cache_directory_is_not_a_reference(shipped, rel):
    (shipped / OLD).write_bytes(PNG)
    (shipped / rel).parent.mkdir(parents=True, exist_ok=True)
    (shipped / rel).write_text("drop old.png from the landing\n")
    assert f"{OLD}:0: IMG_ORPHAN: {OLD}" in _run(shipped).stdout


def test_a_mention_inside_a_binary_file_is_not_a_reference(shipped):
    (shipped / OLD).write_bytes(PNG)
    (shipped / "static" / "src" / "fonts").mkdir(parents=True)
    (shipped / "static" / "src" / "fonts" / "brand.woff").write_bytes(b"wOFF\0\0 old.png \0")
    assert f"{OLD}:0: IMG_ORPHAN: {OLD}" in _run(shipped).stdout


def test_a_longer_name_containing_the_file_name_does_not_reference_it(shipped):
    (shipped / OLD).write_bytes(PNG)
    (shipped / "README.rst").write_text("See myold.png and old.png.bak\n")
    assert "IMG_ORPHAN" in _rules(_run(shipped))


def test_orphans_are_not_reported_when_files_are_named(shipped):
    (shipped / OLD).write_bytes(PNG)
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
