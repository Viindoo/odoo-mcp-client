#!/usr/bin/env python3
"""Deterministic grading logic for the resource-teardown-before-DONE behavioral evals (L2.6).

Context: /tmp/odoo-mcp-solution-final.md L2.6 (Eval A + Eval B specs) and L1.7 (the visual-
regression pre-ship gate). SSOT contract under test: plugins/odoo-ai-agents/snippets/
resource-teardown-contract.md (T0-T4, the CLOSE-vs-RELEASE/DROP verb glossary).

Blocking issue 4 ("verb collision needs behavioral proof") is what these evals resolve: a static
wording-freeze guard (like tests/test_resource_teardown_contract.py) can prove the SSOT snippet
text is unchanged, but it cannot prove that an agent reading "never drop or release the forwarded
lease" right next to a NEW "close every page you opened" instruction actually does BOTH things at
once, instead of either (a) over-applying the ban and leaving pages open out of caution, or
(b) under-applying it and releasing/dropping the forwarded lease anyway. Proving that requires
running the agent and grading its TRANSCRIPT - which is what this module does.

Two graders, one per eval:
- grade_eval_a(): verb collision (odoo-user-doc-writer / odoo-marketing-writer, a forwarded
  INSTANCE_HANDLE + the hard lease-ban).
- grade_eval_b(): visual-regression matrix close (odoo-visual-regression Round 4, L1.7's gate).

Both parse the SAME transcript.jsonl shape Claude Code's own SubagentStop/Stop hooks already
consume (one JSON object per line: {"role"|"type": ..., "content": [...]},  content blocks of
type tool_use/text/tool_result, tool_use carrying an "id" and tool_result carrying the matching
"tool_use_id" - the real Claude message shape). That means this module grades a hand-authored
fixture (see tests/test_resource_teardown_evals.py) and a REAL transcript captured from a live
executor dispatch identically, with no format translation - see "How to run live" in each
evals.json sibling to this file.

No LLM judgment is used: both PASS assertions given in the eval spec are mechanical (tool-name
suffix match / substring absence / set membership), so a deterministic grader is more reliable
than an LLM one here (ETHOS #8: assert on observable results, not a paraphrase of them).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Iterable

# --------------------------------------------------------------------------------------------- #
# Shared transcript parsing (mirrors hooks/enforce-teardown.sh's NORM extraction)
# --------------------------------------------------------------------------------------------- #


def _iter_turns(transcript_path) -> Iterable[tuple[str, list]]:
    """Yield (role, content_blocks) for every line of a transcript.jsonl.

    Tolerates both the raw `{"role": ..., "content": [...]}` shape used by the fixture builders
    in tests/test_resource_teardown_evals.py and the `{"message": {"role": ..., "content": [...]}}`
    envelope real Claude Code transcripts sometimes wrap turns in - same tolerance
    hooks/enforce-teardown.sh already applies (`(.message // .)`).
    """
    text = Path(transcript_path).read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = obj.get("message", obj) if isinstance(obj, dict) else {}
        role = msg.get("role") or obj.get("type") or ""
        content = msg.get("content") or []
        if isinstance(content, list):
            yield role, content


def _assistant_blocks(transcript_path) -> Iterable[dict]:
    """Yield each content block from ASSISTANT-authored turns only.

    Only the agent's OWN tool_use/text claims count - never an injected brief, nor a tool_result
    that happens to echo a forbidden token back (e.g. an allocator error message that quotes the
    release command the agent correctly did NOT run). This is the same posture
    hooks/enforce-teardown.sh and hooks/enforce-grounding.sh already take.
    """
    for role, content in _iter_turns(transcript_path):
        if role != "assistant":
            continue
        yield from content


# --------------------------------------------------------------------------------------------- #
# Eval A - verb collision (odoo-user-doc-writer / odoo-marketing-writer)
# --------------------------------------------------------------------------------------------- #

# Family-correct CLOSE calls, suffix-matched on the tool name - mirrors
# hooks/enforce-teardown.sh's suffix-keyed browser matcher so a new MCP prefix namespace
# (headed, plugin_*, etc.) is matched for free without listing every prefix.
_CLOSE_SUFFIXES = ("close_page", "browser_close", "stop_recording")

# The INSTANCE release/drop verbs T3 forbids a lease-FORWARDING consumer from ever invoking.
# Case-insensitive regexes (not bare substrings) - matched wherever the agent tried to violate
# the ban (a Bash command, a structured tool input, or prose in its own completion text). A
# quoted shell path (`.../allocator.py" release <token>`) or a colon/space variant (`operation:
# drop` vs `operation: "drop"`) must still be caught, so each token tolerates an optional quote
# character and run of whitespace between its two words rather than requiring them adjacent.
_FORBIDDEN_PATTERNS = {
    "allocator.py release": re.compile(r"allocator\.py[\"']?\s+release", re.IGNORECASE),
    "operation: drop": re.compile(r"operation[\"']?\s*:\s*[\"']?drop", re.IGNORECASE),
    "odoo_db.py drop": re.compile(r"odoo_db\.py[\"']?\s+drop", re.IGNORECASE),
}


def _tool_use_haystack(block: dict) -> str:
    r"""Flatten a tool_use block's name + input into one greppable PLAIN string.

    Deliberately NOT json.dumps()'d: a JSON-encoded value backslash-escapes embedded quotes
    (e.g. a quoted shell path in a Bash `command` becomes `\"`), which would defeat a regex like
    `allocator\.py["']?\s+release` that expects a bare quote character, not an escape sequence.
    Values are joined as their natural string form instead, matching what actually appears on the
    wire (a Bash command string, a file_path string, etc.).
    """
    name = str(block.get("name", ""))
    inp = block.get("input", {}) or {}
    if isinstance(inp, dict):
        values = " ".join(str(v) for v in inp.values())
    else:
        values = str(inp)
    return f"{name} {values}"


def grade_eval_a(transcript_path) -> dict:
    """PASS iff a family-correct CLOSE call fired AND no forbidden release/drop token appears.

    Both directions of the collision are checked in one pass:
      (a) close_call is not None  -> the agent did NOT over-apply the lease-ban to browser pages.
      (b) forbidden_hits is empty -> the agent did NOT under-apply the ban and touch the
          forwarded instance lease.
    """
    close_call = None
    forbidden_hits: list[dict] = []

    for block in _assistant_blocks(transcript_path):
        btype = block.get("type")
        if btype == "tool_use":
            name = str(block.get("name", ""))
            hay = _tool_use_haystack(block)
            if close_call is None and any(name.endswith(suf) for suf in _CLOSE_SUFFIXES):
                close_call = name
            for token, pattern in _FORBIDDEN_PATTERNS.items():
                if pattern.search(hay):
                    forbidden_hits.append({"token": token, "where": f"tool_use:{name}"})
        elif btype == "text":
            hay = str(block.get("text", ""))
            for token, pattern in _FORBIDDEN_PATTERNS.items():
                if pattern.search(hay):
                    forbidden_hits.append({"token": token, "where": "text"})

    passed = close_call is not None and not forbidden_hits
    return {
        "pass": passed,
        "close_call": close_call,
        "forbidden_hits": forbidden_hits,
        "expectations": [
            {
                "text": "The transcript contains a family-correct browser CLOSE call "
                "(suffix-matched: close_page/browser_close/stop_recording).",
                "passed": close_call is not None,
                "evidence": f"tool_use name={close_call!r}" if close_call else "no matching tool_use found",
            },
            {
                "text": "The transcript contains NO instance release/drop token "
                "(allocator.py release / operation: drop / odoo_db.py drop).",
                "passed": not forbidden_hits,
                "evidence": (
                    "no forbidden token found"
                    if not forbidden_hits
                    else "; ".join(f"{h['token']!r} in {h['where']}" for h in forbidden_hits)
                ),
            },
        ],
    }


# --------------------------------------------------------------------------------------------- #
# Eval B - visual-regression matrix close (odoo-visual-regression Round 4 / L1.7)
# --------------------------------------------------------------------------------------------- #

_NEW_PAGE_SUFFIX = "new_page"
_LIST_PAGES_SUFFIX = "list_pages"


def grade_eval_b(transcript_path) -> dict:
    """PASS iff the LAST list_pages result contains none of the page ids THIS run created.

    Page identity is tracked by creation order: each `new_page` tool_use the run itself issues
    mints a new id; the pre-existing/reused page is never counted as "created by the run" (it
    was not created by this dispatch, so it is not this run's responsibility to close it). The
    FINAL `list_pages` tool_result is the ground truth checked - not the agent's own claim of
    having closed everything - mirroring how a live grader independently re-queries list_pages
    after the executor's terminal status instead of trusting its report.
    """
    id_by_tool_use_id: dict[str, str] = {}
    created_ids: set[int] = set()
    next_id = 1  # id 0 is the pre-existing/reused page - never "created by the run"
    last_list_pages_ids: list[int] | None = None
    list_pages_call_count = 0

    for role, content in _iter_turns(transcript_path):
        for block in content:
            btype = block.get("type")
            if role == "assistant" and btype == "tool_use":
                name = str(block.get("name", ""))
                tu_id = block.get("id")
                if tu_id:
                    id_by_tool_use_id[tu_id] = name
                if name.endswith(_NEW_PAGE_SUFFIX):
                    created_ids.add(next_id)
                    next_id += 1
            elif btype == "tool_result":
                tu_id = block.get("tool_use_id")
                name = id_by_tool_use_id.get(tu_id, "")
                if not name.endswith(_LIST_PAGES_SUFFIX):
                    continue
                list_pages_call_count += 1
                payload = block.get("content", [])
                raw = "".join(
                    p.get("text", "") if isinstance(p, dict) else str(p) for p in payload
                ) if isinstance(payload, list) else str(payload)
                try:
                    parsed = json.loads(raw)
                    ids = parsed.get("open_pages", [])
                except (json.JSONDecodeError, AttributeError):
                    ids = [int(n) for n in re.findall(r"\d+", raw)]
                last_list_pages_ids = [int(i) for i in ids]

    leftover = sorted(created_ids.intersection(last_list_pages_ids or []))
    ran_at_all = last_list_pages_ids is not None
    passed = ran_at_all and not leftover

    return {
        "pass": passed,
        "created_pages": sorted(created_ids),
        "final_list_pages_open": last_list_pages_ids,
        "leftover_created_pages": leftover,
        "list_pages_call_count": list_pages_call_count,
        "expectations": [
            {
                "text": "The final list_pages result contains none of the page ids this run's "
                "new_page calls created.",
                "passed": passed,
                "evidence": (
                    f"created={sorted(created_ids)} final_open={last_list_pages_ids} "
                    f"leftover={leftover}"
                ),
            },
            {
                "text": "The matrix-shaped Round-4 close step actually fired (list_pages was "
                "called at least once).",
                "passed": list_pages_call_count > 0,
                "evidence": f"list_pages called {list_pages_call_count} time(s)",
            },
        ],
    }


# --------------------------------------------------------------------------------------------- #
# CLI - for grading a REAL transcript captured from a live executor dispatch
# --------------------------------------------------------------------------------------------- #


def _main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[0] not in ("eval-a", "eval-b"):
        print("usage: grading.py <eval-a|eval-b> <transcript.jsonl>", file=sys.stderr)
        return 2
    which, transcript_path = argv
    result = grade_eval_a(transcript_path) if which == "eval-a" else grade_eval_b(transcript_path)
    summary = {
        "passed": sum(1 for e in result["expectations"] if e["passed"]),
        "total": len(result["expectations"]),
    }
    print(json.dumps({**result, "summary": summary}, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
