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
An image in an RST also has to fit the page: both stores load Bootstrap 5 and size an RST image by
its file's pixel width, so a screenshot captured at device pixel ratio 2 overflows the page unless
the directive carries `img-fluid` and the `:width:` of its intended CSS width.
Each test builds a small module in a temp dir, writes ONE reference, and runs the gate's `main`
in this process (the rules are the subject, and a fresh interpreter per case is most of the cost);
the process boundary itself - the entry point's exit status, `--help`, the interpreter floor - is
exercised through real subprocesses in the "CLI contract" section.
"""
import contextlib
import importlib.util
import io
import os
import struct
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "plugins" / "odoo-ai-agents" / "scripts" / "lib" / "doc_refs_check.py"
SERIES = "17.0"
PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"


def _png(width, height=400):
    return (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + struct.pack(">II", width, height)
            + b"\x08\x06\x00\x00\x00")


def _gif(width, height=400):
    return b"GIF89a" + struct.pack("<HH", width, height) + b"\x00\x00\x00"


def _jpeg(width, height=400):
    """SOI, one APP0 segment the reader must skip, then the SOF0 that carries the size."""
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    sof0 = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, height, width, 1) + b"\x01\x11\x00"
    return b"\xff\xd8" + app0 + sof0 + b"\xff\xd9"


# A file of 1280 px is a 640 px capture at device pixel ratio 2.
FILE_PX = 1280
FIT = "   :class: img-fluid d-block mx-auto\n   :width: 600px\n"


def _img(ref, directive="image", options=FIT):
    """One well-fitted RST image directive; `directive` is image, figure or sub (substitution)."""
    head = {"image": ".. image:: ", "figure": ".. figure:: ", "sub": ".. |logo| image:: "}[directive]
    if directive == "sub":
        options = options.replace(" d-block mx-auto", "")
    return head + ref + "\n" + options
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
        p.write_bytes(_png(FILE_PX, FILE_PX // 2) if rel.endswith("main_screenshot.png")
                      else _png(FILE_PX))
    (tmp_path / "addons" / "sale" / "static").mkdir(parents=True)
    (tmp_path / "addons" / "sale" / "static" / "x.png").write_bytes(PNG)
    _manifest(mod, "static/description/main_screenshot.png")
    return mod


def _manifest(module, *images):
    (module / "__manifest__.py").write_text(
        "{'name': 'X', 'images': [%s]}\n" % ", ".join(repr(i) for i in images))


_spec = importlib.util.spec_from_file_location("doc_refs_check", GATE)
_gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_gate)


class _Result:
    def __init__(self, returncode, stdout, stderr):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def _main(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = _gate.main(list(argv))
    return _Result(code, out.getvalue(), err.getvalue())


def _run(module, *files, series=SERIES):
    return _main("--module-root", str(module), "--series", series, *files)


def _rst(module, body):
    (module / "doc" / "index.rst").write_text(textwrap.dedent(body), encoding="utf-8")
    return _run(module, "doc/index.rst")


def _html(module, body):
    (module / "static" / "description" / "index.html").write_text(textwrap.dedent(body),
                                                                    encoding="utf-8")
    return _run(module, "static/description/index.html")


def _readme(module, ref):
    (module / "README.rst").write_text(_img(ref))
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
    _clean(_rst(module, _img(ref)))


@pytest.mark.parametrize("ref", [
    "https://raw.githubusercontent.com/acme/branding/0123abc/logo/acme-logo.svg",
    "https://cdn.example.com/brand/logo%20v2.png",
])
def test_a_public_https_image_passes_pinned_or_not(module, ref):
    """A vendor logo at a public URL is displayed as is by the stores: no existence, location,
    name or orphan check applies, and the gate does not check pinning (the second URL is not
    pinned to a revision)."""
    _clean(_rst(module, _img(ref)))
    _clean(_html(module, f'<img src="{ref}"/><img src="./main_screenshot.png"/>\n'))
    _clean(_readme(module, ref))


@pytest.mark.parametrize("name", ["caf\u00e9.png", "shot(1).png", "a+b.png", "form,v2.png"])
def test_a_module_image_name_outside_the_safe_set_is_flagged(module, name):
    (module / "static" / "description" / "assets" / name).write_bytes(PNG)
    _only(_rst(module, _img(f"assets/{name}")), "IMG_NAME")
    _only(_html(module, f'<img src="./main_screenshot.png"/><img src="./assets/{name}"/>\n'),
          "IMG_NAME")
    _manifest(module, "static/description/assets/" + name)
    assert _rules(_run(module, "__manifest__.py")) == ["IMG_NAME", "MANIFEST_COVER"]


def test_an_html_image_whose_decoded_name_has_a_space_is_flagged(module):
    (module / "static" / "description" / "assets" / "old one.png").write_bytes(PNG)
    _only(_html(module, '<img src="./main_screenshot.png"/><img src="./assets/old%20one.png"/>'),
          "IMG_NAME")


def test_a_module_image_name_in_the_safe_set_passes(module):
    (module / "static" / "description" / "assets" / "Sales_Order-form.v2.png").write_bytes(PNG)
    _clean(_rst(module, _img("assets/Sales_Order-form.v2.png")))


def test_a_guide_image_in_assets_or_the_root_cover_passes_in_every_directive(module):
    (module / "static" / "description" / "main_screenshot.vi_VN.png").write_bytes(PNG)
    _clean(_rst(module, "\n".join([
        _img("assets/form.png"), _img("main_screenshot.png", "figure"),
        _img("assets/form.png", "sub"), _img("main_screenshot.vi_VN.png")])))


@pytest.mark.parametrize("directive", ["image", "figure", "sub"])
def test_every_rst_image_directive_is_checked(module, directive):
    """A figure or a substitution image is as much a published image as a plain one."""
    proc = _rst(module, _img("../static/description/assets/form.png",
                             {"image": "image", "figure": "figure", "sub": "sub"}[directive]))
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
    _only(_rst(module, _img(ref)), "IMG_NOT_IN_ASSETS")


@pytest.mark.parametrize("ref", ["assets/raw.png", "main_screenshot.vi_VN.png"])
def test_a_guide_image_in_its_form_but_absent_from_static_description_is_missing(module, ref):
    proc = _rst(module, _img(ref))
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
# image fit on the stores (RST only)
# --------------------------------------------------------------------------- #
DIRECTIVES = ["image", "figure", "sub"]


def _options(*lines):
    return "".join("   " + line + "\n" for line in lines)


@pytest.mark.parametrize("directive", DIRECTIVES)
def test_a_well_fitted_image_passes_in_every_directive(module, directive):
    _clean(_rst(module, _img("assets/form.png", directive)))
    _clean(_readme(module, "static/description/assets/form.png"))


@pytest.mark.parametrize("classes", [
    None, "img-fluid", "img-fluid d-block", "img-fluid mx-auto", "d-block mx-auto",
    "img-fluidx d-block mx-auto",
])
@pytest.mark.parametrize("directive", ["image", "figure"])
def test_a_block_image_without_the_full_fluid_class_is_flagged(module, directive, classes):
    """A block image must be capped at the column (img-fluid) and centred as a block (d-block
    mx-auto); the stores style no `align-center`."""
    lines = [":width: 600px"] + ([":class: " + classes] if classes else [])
    proc = _rst(module, _img("assets/form.png", directive, _options(*lines)))
    assert proc.stdout == "doc/index.rst:1: IMG_NOT_FLUID: assets/form.png\n"
    assert proc.returncode == 1


@pytest.mark.parametrize("classes", [None, "d-block", "img-fluid d-block", "img-fluid mx-auto"])
def test_an_inline_substitution_image_must_be_fluid_and_must_not_be_a_block(module, classes):
    """`d-block` / `mx-auto` on an inline image would break the line around it."""
    lines = [":width: 600px"] + ([":class: " + classes] if classes else [])
    proc = _rst(module, ".. |logo| image:: assets/form.png\n" + _options(*lines))
    assert proc.stdout == "doc/index.rst:1: IMG_NOT_FLUID: assets/form.png\n"


def test_an_external_image_needs_the_fluid_class_but_no_width(module):
    ref = "https://cdn.example.com/brand/logo.png"
    _clean(_rst(module, _img(ref, options=_options(":class: img-fluid d-block mx-auto"))))
    _clean(_rst(module, _img(ref, "sub", _options(":class: img-fluid"))))
    proc = _rst(module, _img(ref, options=""))
    assert proc.stdout == f"doc/index.rst:1: IMG_NOT_FLUID: {ref}\n"


def test_the_fluid_rule_reads_the_option_block_of_the_right_image(module):
    """The second image is the unfitted one; the finding names its line, not the first's."""
    proc = _rst(module, _img("assets/form.png") + "\n" + ".. image:: assets/form.png\n"
                + _options(":width: 600px"))
    assert proc.stdout == "doc/index.rst:5: IMG_NOT_FLUID: assets/form.png\n"


@pytest.mark.parametrize("option", [
    ":width: 100%", ":width: 50 %", ":scale: 50", ":height: 300px", ":align: center",
    ":align: left",
])
@pytest.mark.parametrize("directive", DIRECTIVES)
def test_an_option_that_stretches_or_does_nothing_on_the_stores_is_flagged(module, directive,
                                                                         option):
    options = FIT.replace(":width: 600px", ":width: 600px\n   " + option) \
        if not option.startswith(":width:") else FIT.replace(":width: 600px", option)
    proc = _rst(module, _img("assets/form.png", directive, options))
    assert proc.stdout == "doc/index.rst:1: IMG_STRETCHED: assets/form.png\n", proc.stdout


def test_the_w_100_class_is_flagged_as_stretched(module):
    options = _options(":class: img-fluid d-block mx-auto w-100", ":width: 600px")
    proc = _rst(module, _img("assets/form.png", options=options))
    assert proc.stdout == "doc/index.rst:1: IMG_STRETCHED: assets/form.png\n"


def test_an_external_image_may_not_stretch_either(module):
    options = _options(":class: img-fluid d-block mx-auto", ":align: center")
    proc = _rst(module, _img("https://cdn.example.com/logo.png", options=options))
    assert _rules(proc) == ["IMG_STRETCHED"], proc.stdout


@pytest.mark.parametrize("width", [None, "600", "40em", "auto"])
@pytest.mark.parametrize("directive", DIRECTIVES)
def test_a_module_image_without_a_px_width_is_flagged(module, directive, width):
    lines = [":class: img-fluid" if directive == "sub" else ":class: img-fluid d-block mx-auto"]
    if width:
        lines.append(":width: " + width)
    proc = _rst(module, _img("assets/form.png", directive, _options(*lines)))
    assert proc.stdout == "doc/index.rst:1: IMG_NO_WIDTH: assets/form.png\n", proc.stdout


def test_the_cover_image_in_a_guide_needs_a_width_too(module):
    proc = _rst(module, _img("main_screenshot.png", options=_options(
        ":class: img-fluid d-block mx-auto")))
    assert proc.stdout == "doc/index.rst:1: IMG_NO_WIDTH: main_screenshot.png\n"


@pytest.mark.parametrize("maker,name", [(_png, "p.png"), (_gif, "g.gif"), (_jpeg, "j.jpg")])
def test_a_width_above_the_files_pixel_width_is_upscaled_for_png_gif_and_jpeg(module, maker,
                                                                             name):
    """The page would enlarge the image past its pixels - blurry; the limit is the file's own
    pixel width, so exactly equal is fine."""
    (module / "static" / "description" / "assets" / name).write_bytes(maker(500))
    for width, clean in (("500px", True), ("501px", False), ("250px", True)):
        options = FIT.replace("600px", width)
        proc = _rst(module, _img("assets/" + name, options=options))
        if clean:
            _clean(proc)
        else:
            assert proc.stdout == f"doc/index.rst:1: IMG_UPSCALED: assets/{name}\n", proc.stdout


@pytest.mark.parametrize("directive", DIRECTIVES)
def test_upscaling_is_flagged_in_every_directive_and_in_a_readme(module, directive):
    wide = FIT.replace("600px", "%dpx" % (FILE_PX + 1))
    proc = _rst(module, _img("assets/form.png", directive, wide))
    assert proc.stdout == "doc/index.rst:1: IMG_UPSCALED: assets/form.png\n"
    (module / "README.rst").write_text(_img("static/description/assets/form.png", options=wide))
    proc = _run(module, "README.rst")
    assert proc.stdout == "README.rst:1: IMG_UPSCALED: static/description/assets/form.png\n"


def test_an_unreadable_image_header_does_not_make_the_width_upscaled(module):
    """A file whose size cannot be read is judged by the other rules only."""
    (module / "static" / "description" / "assets" / "broken.png").write_bytes(b"not an image")
    _clean(_rst(module, _img("assets/broken.png")))


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

        Call `us <tel:+000000000>`_ or jump to `top <#top>`_.
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
    assert proc.stdout == ("__manifest__.py:4: MANIFEST_IMAGES_COUNT: 2 images\n"
                           "__manifest__.py:6: MANIFEST_IMAGE: %s\n" % entry)
    assert proc.returncode == 1


@pytest.mark.parametrize("cover", [
    "main_screenshot.png", "main_screenshot.gif", "main_screenshot.jpeg", "main_screenshot.jpg",
])
def test_the_main_screenshot_cover_alone_passes(module, cover):
    (module / "static" / "description" / cover).write_bytes(PNG)
    _manifest(module, "static/description/" + cover)
    _clean(_run(module, "__manifest__.py"))


@pytest.mark.parametrize("extra", [
    "static/description/assets/form.png", "static/description/main_screenshot.vi_VN.png",
])
def test_a_manifest_with_more_than_one_image_has_one_count_finding_at_the_list(module, extra):
    (module / "static" / "description" / "main_screenshot.vi_VN.png").write_bytes(PNG)
    (module / "__manifest__.py").write_text(
        "{\n    'name': 'X',\n    'images': [\n        'static/description/main_screenshot.png',\n"
        "        %r,\n        'static/description/assets/form.png',\n    ],\n}\n" % extra)
    proc = _run(module, "__manifest__.py")
    assert proc.stdout == "__manifest__.py:3: MANIFEST_IMAGES_COUNT: 3 images\n"
    assert proc.returncode == 1


def test_a_manifest_with_no_images_is_clean(module):
    _manifest(module)
    _clean(_run(module, "__manifest__.py"))


@pytest.mark.parametrize("size,ok", [
    ((1280, 640), True), ((1200, 600), True), ((1280, 634), True), ((1280, 646), True),
    ((1280, 633), False), ((1280, 647), False), ((1280, 1280), False), ((1280, 320), False),
])
def test_the_cover_must_be_two_to_one_within_one_percent(module, size, ok):
    (module / "static" / "description" / "main_screenshot.png").write_bytes(_png(*size))
    proc = _run(module, "__manifest__.py")
    if ok:
        _clean(proc)
    else:
        assert proc.stdout == ("__manifest__.py:1: MANIFEST_COVER_RATIO: %dx%d\n" % size)
        assert proc.returncode == 1


@pytest.mark.parametrize("maker", [_gif, _jpeg])
def test_the_cover_ratio_reads_gif_and_jpeg_headers(module, maker):
    ext = "gif" if maker is _gif else "jpg"
    (module / "static" / "description" / f"main_screenshot.{ext}").write_bytes(maker(1280, 1280))
    _manifest(module, f"static/description/main_screenshot.{ext}")
    _only(_run(module, "__manifest__.py"), "MANIFEST_COVER_RATIO")
    (module / "static" / "description" / f"main_screenshot.{ext}").write_bytes(maker(1280, 640))
    _clean(_run(module, "__manifest__.py"))


def test_a_cover_whose_size_cannot_be_read_or_that_is_missing_has_no_ratio_finding(module):
    (module / "static" / "description" / "main_screenshot.png").write_bytes(PNG)
    _clean(_run(module, "__manifest__.py"))
    (module / "static" / "description" / "main_screenshot.png").unlink()
    _only(_run(module, "__manifest__.py"), "MANIFEST_IMAGE")


@pytest.mark.parametrize("cover", [
    "static/description/assets/form.png", "static/description/main_screenshot.vi_VN.png",
    "static/description/assets/main_screenshot.png",
])
def test_a_first_image_that_is_not_the_root_main_screenshot_is_not_the_cover(module, cover):
    for rel in (cover, "static/description/assets/main_screenshot.png"):
        (module / rel).write_bytes(PNG)
    _manifest(module, cover)
    _only(_run(module, "__manifest__.py"), "MANIFEST_COVER")


def test_another_screenshot_named_image_at_the_root_is_neither_the_cover_nor_in_assets(module):
    (module / "static" / "description" / "banner_screenshot.jpg").write_bytes(PNG)
    _manifest(module, "static/description/banner_screenshot.jpg")
    assert _rules(_run(module, "__manifest__.py")) == ["MANIFEST_IMAGE", "MANIFEST_COVER"]


# --------------------------------------------------------------------------- #
# the page may show the cover or not
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("markup", [
    '<p>x</p>\n<img src="./assets/form.png"/>\n',
    '<section><h1>Title</h1></section>',
    '<img src="./main_screenshot.png"/>',
    '<img src="main_screenshot.png"/>',
])
def test_a_page_is_valid_whether_or_not_it_embeds_the_cover(module, markup):
    _clean(_html(module, markup))


def test_a_cover_reference_resolving_elsewhere_keeps_failing_the_path_rules(module):
    (module / "static" / "description" / "img").mkdir(exist_ok=True)
    (module / "static" / "description" / "img" / "main_screenshot.png").write_bytes(PNG)
    _flags(_html(module, '<img src="./img/main_screenshot.png"/>'), "IMG_NOT_IN_ASSETS")


def test_a_page_may_still_reference_a_locale_cover(module):
    (module / "static" / "description" / "main_screenshot.vi_VN.png").write_bytes(PNG)
    _clean(_html(module, '<img src="./main_screenshot.vi_VN.png"/>'))


# --------------------------------------------------------------------------- #
# the page does not repeat the series
# --------------------------------------------------------------------------- #
def test_a_store_page_naming_the_series_in_its_text_is_flagged_at_its_line(module):
    proc = _html(module, "<section>\n<h1>Works on 17.0</h1>\n<p>text\nmore 17.0.</p></section>")
    assert proc.stdout == ("static/description/index.html:2: PAGE_NAMES_SERIES: 17.0\n"
                           "static/description/index.html:4: PAGE_NAMES_SERIES: 17.0\n")
    assert proc.returncode == 1


@pytest.mark.parametrize("markup", [
    "<p>version 117.0 and 17.05 and 17.0.1 and 1.17.0 and 17.0.3</p>",
    '<a href="https://docs.acme.com/17.0">docs.acme.com/guide</a><img alt="17.0" src="./assets/form.png">',
    "<!-- 17.0 -->",
    "<script>var v = '17.0';</script><style>/* 17.0 */</style>",
    "<p>version 18.0</p>",
])
def test_the_series_inside_a_longer_number_an_attribute_a_comment_or_code_is_not_named(
        module, markup):
    _clean(_html(module, markup))


def test_a_translated_store_page_must_not_name_the_series_either(module):
    page = module / "static" / "description" / "index_vi_VN.html"
    page.write_text("<p>Phien ban 17.0</p>", encoding="utf-8")
    _only(_run(module, "static/description/index_vi_VN.html"), "PAGE_NAMES_SERIES")


def test_the_series_in_a_guide_is_not_flagged(module):
    _clean(_rst(module, "Title\n=====\n\nWorks on 17.0\n"))


# --------------------------------------------------------------------------- #
# orphans (whole-module mode)
# --------------------------------------------------------------------------- #
OLD = "static/description/assets/old.png"


@pytest.fixture
def shipped(module):
    """A module whose every image is referenced: the whole-module run is clean."""
    for rel in STRAY:
        (module / rel).unlink()
    (module / "doc" / "index.rst").write_text(_img("assets/form.png"))
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
        _img("assets/form.png") + "\n" + _img("../static/description/form.png"))
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
    proc = _main(*[a.replace("{mod}", str(module)) for a in args])
    assert proc.returncode == 2, proc.stdout + proc.stderr


def test_the_entry_point_exits_with_the_verdict_of_the_check(module):
    """The process boundary: exit 1 and a `file:line: RULE: ref` line for a finding, exit 0 and
    nothing for a clean module."""
    argv = [sys.executable, str(GATE), "--module-root", str(module), "--series", SERIES,
            "doc/index.rst"]
    (module / "doc" / "index.rst").write_text(".. image:: /abs.png\n")
    flagged = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    assert flagged.returncode == 1 and flagged.stdout == "doc/index.rst:1: IMG_NOT_RELATIVE: /abs.png\n"
    (module / "doc" / "index.rst").write_text(_img("assets/form.png"))
    clean = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    assert clean.returncode == 0 and clean.stdout == ""


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
    assert proc.stderr.strip(), "the refusal must tell the caller what to do, not exit silently"


def test_the_gate_parses_on_python_3_8_grammar():
    import ast
    ast.parse(GATE.read_text(encoding="utf-8"), feature_version=(3, 8))


# --------------------------------------------------------------------------- #
# published contact details: no address, no mailto, a link that shows its URL
# --------------------------------------------------------------------------- #
def test_a_mailto_link_is_flagged_in_a_page_and_in_a_guide(module):
    _only(_html(module, '<section><img src="./main_screenshot.png"><a href="mailto:sales@acme-erp.com">Contact</a></section>'),
          "LINK_MAILTO")
    proc = _rst(module, """
        Contact
        =======

        `Write to us <mailto:sales@acme-erp.com>`__
        """)
    assert proc.returncode == 1
    assert set(_rules(proc)) == {"LINK_MAILTO", "EMAIL_ADDRESS"}, proc.stdout


@pytest.mark.parametrize("text", [
    "Reach sales at sales@acme-erp.com today.",
    "Reach sales at sales [at] acme-erp [dot] com today.",
    "Reach sales at sales (at) acme-erp.com today.",
])
def test_an_email_address_in_prose_is_flagged_plain_or_obfuscated(module, text):
    _only(_rst(module, "Title\n=====\n\n%s\n" % text), "EMAIL_ADDRESS")
    _only(_html(module, '<section><img src="./main_screenshot.png"><p>%s</p></section>' % text), "EMAIL_ADDRESS")


def test_an_email_in_an_attribute_is_flagged(module):
    _only(_html(module, '<section><img src="./main_screenshot.png"><img src="assets/form.png" '
                        'alt="write to sales@acme-erp.com"></section>'), "EMAIL_ADDRESS")


@pytest.mark.parametrize("text", [
    "A sample login such as admin@example.com works on the demo database.",
    "The decorator @api.depends lists the fields the compute reads.",
    "Mention a colleague with @ in the chatter.",
])
def test_an_example_address_or_a_bare_at_sign_passes(module, text):
    _clean(_rst(module, "Title\n=====\n\n%s\n" % text))


def test_a_store_page_link_whose_text_hides_its_url_is_flagged(module):
    _only(_html(module, '<section><img src="./main_screenshot.png">'
                        '<a href="https://support.acme-erp.com/tickets">Open a ticket</a></section>'), "LINK_TEXT_HIDES_URL")


@pytest.mark.parametrize("markup", [
    '<a href="https://support.acme-erp.com/tickets">support.acme-erp.com/tickets</a>',
    '<a href="https://www.acme-erp.com/contact">Pre-sales: www.acme-erp.com/contact</a>',
    '<a href="/apps/modules/17.0/sale_delivery_window">this module</a>',
    '<a href="#faq">FAQ</a>',
    '<a href="https://www.youtube.com/watch?v=abc123">youtube.com/watch?v=abc123</a>',
])
def test_a_store_page_link_that_shows_its_host_or_stays_in_the_store_passes(module, markup):
    _clean(_html(module, '<section><img src="./main_screenshot.png">%s</section>' % markup))


def test_a_guide_link_is_not_held_to_the_store_text_rule(module):
    _clean(_rst(module, "Title\n=====\n\n`Open a ticket <https://support.acme-erp.com/t>`__\n"))


def test_a_store_link_to_a_module_that_is_not_in_the_addons_path_is_reported(tmp_path):
    """The EXTENSIONS cards link sibling modules root-relative; with --addons-path the gate refuses a
    link to a module nobody ships (a name from memory)."""
    addons = tmp_path / "addons"
    for name in ("my_app", "my_app_extra"):
        (addons / name).mkdir(parents=True)
        (addons / name / "__manifest__.py").write_text("{'name': %r, 'depends': ['base']}" % name)
    page = addons / "my_app" / "static" / "description"
    page.mkdir(parents=True)
    (page / "index.html").write_text(
        '<a href="/apps/modules/17.0/my_app_extra">Extra</a> <a href="/apps/modules/17.0/my_app_ghost">Ghost</a>')
    base = ["--module-root", str(addons / "my_app"), "--series", "17.0"]
    with_path = _main(*base, "--addons-path", str(addons), str(page / "index.html"))
    assert with_path.returncode != 0
    unknown = [l for l in with_path.stdout.splitlines() if "LINK_MODULE_UNKNOWN" in l]
    assert len(unknown) == 1 and "my_app_ghost" in unknown[0] and "my_app_extra" not in unknown[0]
    without = _main(*base, str(page / "index.html"))
    assert "LINK_MODULE_UNKNOWN" not in without.stdout   # the check needs the directories


# --------------------------------------------------------------------------- #
# store page size and YouTube links
# --------------------------------------------------------------------------- #
def _words(count):
    return " ".join(["word"] * count)


def _page(words=0, images=1, extra=""):
    shots = '<img src="./main_screenshot.png">' + '<img src="./assets/form.png">' * (images - 1)
    return '<section>%s<p>%s</p>%s</section>' % (shots, _words(words), extra)


def test_a_store_page_over_900_visible_words_is_too_long(module):
    _only(_html(module, _page(words=901)), "PAGE_TOO_LONG")


def test_a_store_page_of_exactly_900_visible_words_is_clean(module):
    _clean(_html(module, _page(words=900)))


def test_words_in_a_comment_a_script_or_a_style_do_not_count(module):
    hidden = ("<!-- %s --><script>var s = '%s';</script><style>/* %s */</style>"
              % (_words(400), _words(400), _words(400)))
    _clean(_html(module, _page(words=700, extra=hidden)))


def test_a_translated_store_page_is_held_to_the_word_limit_too(module):
    page = module / "static" / "description" / "index_vi_VN.html"
    page.write_text(_page(words=901), encoding="utf-8")
    _only(_run(module, "static/description/index_vi_VN.html"), "PAGE_TOO_LONG")


def test_a_store_page_with_more_than_8_images_has_too_many(module):
    _only(_html(module, _page(images=9)), "PAGE_TOO_MANY_IMAGES")


def test_a_store_page_with_exactly_8_images_is_clean(module):
    _clean(_html(module, _page(images=8)))


# the screenshot carousel of reports and dashboards
SLIDE = '<div class="carousel-item%s"><img src="./assets/form.png" alt="r"></div>'


def _carousel(slides=3, active=(0,), cid="reports", indexed=None, ride="", slide_html=None,
              outer_images=0):
    items = "".join((slide_html or SLIDE) % (" active" if n in active else "")
                    for n in range(slides))
    listed = slides if indexed is None else indexed
    index = "".join('<button data-bs-target="#%s" data-bs-slide-to="%d">Report %d</button>'
                    % (cid, n, n) for n in range(listed))
    idattr = ' id="%s"' % cid if cid else ""
    return _page(images=outer_images + 1, extra=(
        '<div class="carousel slide"%s%s><div class="carousel-inner">%s</div></div>%s'
        % (idattr, ride, items, index)))


def test_a_correct_carousel_beside_8_images_raises_no_carousel_or_image_finding(module):
    _clean(_html(module, _carousel(slides=5, outer_images=7)))


def test_carousel_slides_are_not_counted_by_page_too_many_images(module):
    _clean(_html(module, _carousel(slides=5, outer_images=7)))
    _only(_html(module, _carousel(slides=5, outer_images=8)), "PAGE_TOO_MANY_IMAGES")


def test_carousel_too_many_slides_flags_6_and_passes_5(module):
    _only(_html(module, _carousel(slides=6)), "CAROUSEL_TOO_MANY_SLIDES")
    _clean(_html(module, _carousel(slides=5)))


def test_carousel_single_slide_flags_one_and_passes_two(module):
    _only(_html(module, _carousel(slides=1)), "CAROUSEL_SINGLE_SLIDE")
    _clean(_html(module, _carousel(slides=2)))


@pytest.mark.parametrize("active", [(), (0, 1)])
def test_carousel_active_flags_none_or_several_and_passes_one(module, active):
    _only(_html(module, _carousel(active=active)), "CAROUSEL_ACTIVE")
    _clean(_html(module, _carousel(active=(1,))))


def test_carousel_autoplay_flags_data_bs_ride_and_passes_without(module):
    _only(_html(module, _carousel(ride=' data-bs-ride="carousel"')), "CAROUSEL_AUTOPLAY")
    _clean(_html(module, _carousel()))


@pytest.mark.parametrize("kwargs", [{"indexed": 2}, {"indexed": 4}, {"cid": ""}])
def test_carousel_index_flags_a_wrong_count_or_a_missing_id(module, kwargs):
    _only(_html(module, _carousel(**kwargs)), "CAROUSEL_INDEX")
    _clean(_html(module, _carousel(indexed=3)))


def test_carousel_index_counts_only_links_to_its_own_id(module):
    page = _carousel().replace("#reports", "#other", 1)
    _only(_html(module, page), "CAROUSEL_INDEX")


@pytest.mark.parametrize("slide", [
    '<div class="carousel-item%s"></div>',
    '<div class="carousel-item%s"><img src="./assets/form.png"><img src="./assets/form.png"></div>',
])
def test_carousel_slide_image_flags_a_slide_without_exactly_one_img(module, slide):
    proc = _html(module, _carousel(slide_html=slide))
    assert "CAROUSEL_SLIDE_IMAGE" in _rules(proc), proc.stdout
    _clean(_html(module, _carousel()))


def test_carousel_more_than_one_flags_a_second_carousel(module):
    page = _carousel() + _carousel(cid="more")
    _only(_html(module, page), "CAROUSEL_MORE_THAN_ONE")
    _clean(_html(module, _carousel()))


def test_a_guide_and_the_readme_are_not_held_to_the_page_size_limits(module):
    body = "Title\n=====\n\n%s\n\n" % _words(900) + "".join(
        _img("assets/form.png") + "\n" for _ in range(9))
    _clean(_rst(module, body))
    (module / "README.rst").write_text("Title\n=====\n\n%s\n\n" % _words(900) + "".join(
        _img("static/description/assets/form.png") + "\n" for _ in range(9)))
    _clean(_run(module, "README.rst"))


@pytest.mark.parametrize("markup", [
    '<a href="https://www.youtube.com/watch?v=abc"><img src="./assets/x.png" alt="y"></a>',
    '<a href="https://youtu.be/abc"></a>',
    '<a href="https://youtube-nocookie.com/embed/abc"></a>',
])
def test_a_youtube_link_needs_no_visible_text(module, markup):
    shot = module / "static" / "description" / "assets" / "x.png"
    shot.write_bytes(_png(FILE_PX))
    (module / "static" / "description" / "assets" / "form.png").write_bytes(_png(FILE_PX))
    _clean(_html(module, '<section><img src="./main_screenshot.png"><img src="./assets/form.png">%s</section>'
                 % markup))


def test_a_non_youtube_link_with_no_visible_text_is_still_flagged(module):
    _only(_html(module, '<section><img src="./main_screenshot.png">'
                        '<a href="https://vendor.example.com/x"></a></section>'), "LINK_TEXT_HIDES_URL")
