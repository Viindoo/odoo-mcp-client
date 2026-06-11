"""Guard against bare `odoo-semantic` plugin-refs drifting back into the
trigger-phrase / fallback-prose doc surface.

After the plugin split, a lone `odoo-semantic` token in a skill trigger phrase or a
standalone-fallback sentence is ambiguous between the two plugins (`-mcp`/`-skills`).
This test fails if such a bare token appears in that surface, after the legitimate
lexical forms (tool prefix, suffixed plugin name, product URL) are stripped.

Scope is deliberately narrow: config/persona/README/CHANGELOG/snippets legitimately
use the bare server id or the brand and are NOT scanned.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SK = REPO_ROOT / "plugins" / "odoo-ai-agents"

SCANNED = sorted(
    set(SK.glob("skills/**/SKILL.md"))
    | set(SK.glob("skills/**/evals/*.json"))
    | set(SK.glob("commands/*.md"))
    | {REPO_ROOT / "tests" / "smoke" / "runtime_parity.md"}
)

_LEGIT = re.compile(
    r"mcp__odoo-semantic__\w*"
    r"|odoo-semantic-mcp"
    r"|odoo-semantic\.viindoo\.com"
)
_BARE = re.compile(r"odoo-semantic")


@pytest.mark.parametrize(
    "doc", SCANNED, ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_no_bare_odoo_semantic_in_trigger_or_fallback_prose(doc):
    offenders = []
    for n, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
        if _BARE.search(_LEGIT.sub("", line)):
            offenders.append(f"{doc.relative_to(REPO_ROOT)}:{n}: {line.strip()}")
    assert not offenders, (
        "Bare `odoo-semantic` in a trigger phrase or fallback sentence. Use "
        "`odoo-semantic-mcp` / `odoo-ai-agents`, the brand `Odoo Semantic`, "
        "or rephrase (e.g. 'the odoo-semantic-mcp server'):\n" + "\n".join(offenders)
    )
