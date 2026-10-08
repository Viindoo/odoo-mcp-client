"""The App-Store landing's section keys have ONE source: app-store-template.md § Section Map.

The copy `odoo-content-draft` returns labels each block with a `<!-- <KEY> -->` marker, the
skeleton the marketing writer fills opens each section with the same marker, and the writer maps
each copy block onto the section of its key. If any of those spells a key the Section Map does not
define - or the skeleton drops or reorders one - a copy block lands nowhere or a required section
silently disappears from the landing. This file guards that agreement:

  1. the skeleton's markers are exactly the Section Map keys, in Section Map order;
  2. every marker the copy producer, the landing writer or the packaging workflow names is a
     Section Map key;
  3. the copy producer names no marker literal of its own (it defers to the Section Map), so the
     key list cannot fork a second copy there;
  4. every Section Map row carries a Source and a Required value from the legend vocabulary, and at
     least one key is copy-sourced (otherwise the copy producer has nothing to emit).

Each matcher is proved able to fail on planted text before it judges the real files.

Run: python -m pytest tests/test_landing_section_keys.py -v
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
TEMPLATE = PLUGIN / "skills" / "odoo-doc-illustration" / "references" / "app-store-template.md"
CONTENT_DRAFT = PLUGIN / "skills" / "odoo-content-draft" / "SKILL.md"
MARKETING_WRITER = PLUGIN / "agents" / "odoo-marketing-writer.md"
PACKAGING_WORKFLOW = PLUGIN / "workflows" / "module-packaging.workflow.yaml"

MARKER_RE = re.compile(r"<!--\s*([A-Z][A-Z-]+)\s*-->")
SOURCES = {"copy", "catalog", "captures", "manifest", "brief"}
REQUIRED_VALUES = {"Yes", "Recommended", "Optional"}


def _section(text: str, heading_prefix: str) -> str:
    """Body of the `## <n>. ...` section whose heading starts with heading_prefix."""
    m = re.search(rf"^## {re.escape(heading_prefix)}[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert m, f"no section starting '## {heading_prefix}'"
    return m.group(1)


def section_map_rows(template_text: str) -> list[dict[str, str]]:
    """Parse the § 2 Section Map table into rows keyed by its header cells."""
    body = _section(template_text, "2. Section Map")
    lines = [ln.strip() for ln in body.splitlines() if ln.strip().startswith("|")]
    assert len(lines) >= 3, "Section Map has no table"
    header = [c.strip() for c in lines[0].strip("|").split("|")]
    for col in ("Key", "Source", "Required"):
        assert col in header, f"Section Map table lacks a '{col}' column: {header}"
    rows = []
    for ln in lines[2:]:
        cells = [c.strip() for c in ln.strip("|").split("|")]
        assert len(cells) == len(header), f"malformed Section Map row: {ln}"
        rows.append(dict(zip(header, cells)))
    return rows


def skeleton_markers(template_text: str) -> list[str]:
    """Key markers in the § 3 skeleton's html block, in document order."""
    body = _section(template_text, "3. Bootstrap-5 Fragment Skeleton")
    m = re.search(r"```html\n(.*?)\n```", body, re.S)
    assert m, "skeleton has no ```html block"
    return MARKER_RE.findall(m.group(1))


def foreign_markers(consumer_text: str, keys: set[str]) -> set[str]:
    """Markers a consumer names that the Section Map does not define."""
    return set(MARKER_RE.findall(consumer_text)) - keys


# --------------------------------------------------------------------------- #
# Planted cases - each matcher must be able to fail
# --------------------------------------------------------------------------- #
_PLANTED_TEMPLATE = """\
## 2. Section Map (x)

| # | Key | ID | Content | Source | Required |
|---|---|---|---|---|---|
| 1 | HERO | `#a` | x | copy | Yes |
| 2 | KEY-FEATURES | `#b` | x | catalog | Yes |

## 3. Bootstrap-5 Fragment Skeleton (x)

```html
<!-- Banner card -->
<!-- HERO -->
<!-- KEY-FEATURES -->
```

## 4. Next
"""


def test_planted_agreeing_template_parses_and_agrees():
    rows = section_map_rows(_PLANTED_TEMPLATE)
    assert [r["Key"] for r in rows] == ["HERO", "KEY-FEATURES"]
    assert skeleton_markers(_PLANTED_TEMPLATE) == ["HERO", "KEY-FEATURES"]


def test_planted_skeleton_drift_is_detected():
    renamed = _PLANTED_TEMPLATE.replace("<!-- KEY-FEATURES -->", "<!-- FEATURES -->")
    keys = [r["Key"] for r in section_map_rows(renamed)]
    assert skeleton_markers(renamed) != keys


def test_planted_foreign_marker_is_detected():
    keys = {"HERO", "KEY-FEATURES"}
    assert foreign_markers("copy with <!-- HERO --> and <!-- <KEY> -->", keys) == set()
    assert foreign_markers("copy with <!-- HERO --> / <!-- CTA -->", keys) == {"CTA"}


def test_planted_table_without_source_column_is_refused():
    no_source = _PLANTED_TEMPLATE.replace("| Source ", "| Origin ")
    with pytest.raises(AssertionError):
        section_map_rows(no_source)


# --------------------------------------------------------------------------- #
# The real files
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def template_text() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def rows(template_text) -> list[dict[str, str]]:
    return section_map_rows(template_text)


@pytest.fixture(scope="module")
def keys(rows) -> list[str]:
    return [r["Key"] for r in rows]


def test_section_map_keys_are_unique_marker_tokens(keys):
    assert len(keys) == len(set(keys)), f"duplicate Section Map key: {keys}"
    for k in keys:
        assert MARKER_RE.fullmatch(f"<!-- {k} -->"), f"key '{k}' cannot be written as a marker"


def test_section_map_rows_use_the_legend_vocabulary(rows):
    for r in rows:
        assert r["Source"] in SOURCES, f"{r['Key']}: Source '{r['Source']}' not in {SOURCES}"
        assert r["Required"] in REQUIRED_VALUES, (
            f"{r['Key']}: Required '{r['Required']}' not in {REQUIRED_VALUES}"
        )
    assert any(r["Source"] == "copy" for r in rows), "no copy-sourced key - the copy has nothing to fill"


def test_skeleton_sections_are_the_section_map_keys_in_order(template_text, keys):
    markers = skeleton_markers(template_text)
    assert markers == keys, (
        "app-store-template.md § 3 skeleton must open one section per Section Map key, in Section "
        f"Map order.\n  Section Map: {keys}\n  skeleton:    {markers}"
    )


@pytest.mark.parametrize(
    "consumer", [CONTENT_DRAFT, MARKETING_WRITER, PACKAGING_WORKFLOW], ids=lambda p: p.name
)
def test_every_marker_a_consumer_names_is_a_section_map_key(consumer, keys):
    unknown = foreign_markers(consumer.read_text(encoding="utf-8"), set(keys))
    assert not unknown, (
        f"{consumer.relative_to(PLUGIN)} names section marker(s) {sorted(unknown)} that "
        "app-store-template.md § Section Map does not define - a copy block under that label "
        "lands in no section of the landing"
    )


def test_copy_producer_defers_to_the_section_map():
    text = CONTENT_DRAFT.read_text(encoding="utf-8")
    literals = MARKER_RE.findall(text)
    assert not literals, (
        f"odoo-content-draft names marker literal(s) {literals}; it must take the keys from "
        "app-store-template.md § Section Map instead of keeping its own list"
    )
    assert "app-store-template.md" in text and "Section Map" in text, (
        "odoo-content-draft must point at app-store-template.md § Section Map for its landing keys"
    )
