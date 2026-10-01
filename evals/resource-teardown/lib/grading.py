#!/usr/bin/env python3
"""Deterministic grading logic for the resource-teardown-before-DONE behavioral evals.

Behavioral evals for the resource-teardown contract
(plugins/odoo-ai-agents/snippets/resource-teardown-contract.md, T0-T4 + the CLOSE(browser)-vs-
RELEASE/DROP(instance) verb glossary): Eval A proves the CLOSE-vs-RELEASE verb split holds even
under a forwarded-lease collision (T2 vs T3); Eval B proves the visual-regression matrix-close
(T0/T2) ends with one page left, on about:blank.

"Verb collision needs behavioral proof" is what these evals resolve: a static
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

# Calls that put a page on a URL (open it, or reuse it by navigating). A REUSED page is driven
# just like one this agent opened, so it must be closed or returned to about:blank afterwards.
_DRIVE_SUFFIXES = ("new_page", "navigate_page", "browser_navigate", "record_page")

# chrome-devtools cannot close its last page; navigating it to this URL is its close-equivalent.
_BLANK = "about:blank"


def _is_blank_navigation(name: str, inp) -> bool:
    return (name.endswith("navigate_page") and isinstance(inp, dict)
            and str(inp.get("url", "")).strip() == _BLANK)


def _page_id(inp):
    """The pageId a chrome-devtools call carries (page-id routing, on by default since
    chrome-devtools-mcp 1.10), or None."""
    if isinstance(inp, dict) and inp.get("pageId") is not None:
        return str(inp["pageId"])
    return None


def _chrome_page_state(transcript_path) -> tuple[list[tuple[str, str]], tuple[str | None, str | None]]:
    """(live keyed pages, last drive) from the agent's chrome-devtools page calls - the same rule
    hooks/enforce-teardown.sh applies (final-report.sh _chrome_page_calls):
      - live keyed pages: every pageId whose last new_page/navigate_page did not go to
        about:blank and that no later close_page closed, as [(pageId, url)] in first-driven
        order (url "" = a back/forward/reload);
      - last drive: (pageId or None, url or None) of the last new_page/navigate_page call. Its url
        is the fallback signal only when it carries no pageId.
    """
    last: dict[str, str] = {}
    order: list[str] = []
    last_drive: tuple[str | None, str | None] = (None, None)
    for block in _assistant_blocks(transcript_path):
        if block.get("type") != "tool_use":
            continue
        name = str(block.get("name", ""))
        inp = block.get("input", {}) or {}
        pid = _page_id(inp)
        if name.endswith("close_page"):
            if pid is not None:
                last.pop(pid, None)
            continue
        if not name.endswith(("new_page", "navigate_page")):
            continue
        url = inp.get("url") if isinstance(inp, dict) else None
        url = str(url).strip() if url is not None else ""
        last_drive = (pid, url)
        if pid is not None:
            if pid not in order:
                order.append(pid)
            last[pid] = url
    live = [(pid, last[pid]) for pid in order if pid in last and last[pid] != _BLANK]
    return live, last_drive


def _live_pages_expectation(live) -> dict:
    return {
        "text": "Every chrome-devtools page driven by pageId ends closed or on about:blank (a "
        "driven page left on a URL and never closed is a leak, whatever the last call was).",
        "passed": not live,
        "evidence": ("no page left on a URL" if not live else
                     "; ".join(f"page {pid} on {url or 'back/forward/reload'}" for pid, url in live)),
    }


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

# The same two verbs as odoo-local MCP tool calls - the primary way an agent releases or parks a
# lease. Suffix-matched on the tool name, like _CLOSE_SUFFIXES, so any server prefix counts.
_FORBIDDEN_TOOL_SUFFIXES = ("lease_release", "lease_park")


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
    """PASS iff a family-correct CLOSE fired after the last page this agent drove AND no
    forbidden release/drop token appears.

    Both directions of the collision are checked in one pass:
      (a) close_call is not None  -> the agent did NOT over-apply the lease-ban to browser pages.
          A close is close_page / browser_close / stop_recording, or navigate_page to about:blank
          (chrome-devtools refuses to close its last page); it must come AFTER the last drive
          (new_page / navigate_page / browser_navigate / record_page), because a page reused by
          navigating is driven too.
      (b) forbidden_hits is empty -> the agent did NOT under-apply the ban and touch the
          forwarded instance lease.
    Plus, where the calls carry a pageId: no page this agent drove is left on a URL unclosed
    (live_pages) - a close of ANOTHER page does not cover it.
    """
    close_call = None
    forbidden_hits: list[dict] = []

    for block in _assistant_blocks(transcript_path):
        btype = block.get("type")
        if btype == "tool_use":
            name = str(block.get("name", ""))
            inp = block.get("input", {}) or {}
            hay = _tool_use_haystack(block)
            if any(name.endswith(suf) for suf in _CLOSE_SUFFIXES) or _is_blank_navigation(name, inp):
                close_call = name
            elif any(name.endswith(suf) for suf in _DRIVE_SUFFIXES):
                close_call = None
            for token, pattern in _FORBIDDEN_PATTERNS.items():
                if pattern.search(hay):
                    forbidden_hits.append({"token": token, "where": f"tool_use:{name}"})
            for suffix in _FORBIDDEN_TOOL_SUFFIXES:
                if name.endswith(suffix):
                    forbidden_hits.append({"token": suffix, "where": f"tool_use:{name}"})
        elif btype == "text":
            hay = str(block.get("text", ""))
            for token, pattern in _FORBIDDEN_PATTERNS.items():
                if pattern.search(hay):
                    forbidden_hits.append({"token": token, "where": "text"})

    live_pages, _last_drive = _chrome_page_state(transcript_path)
    passed = close_call is not None and not forbidden_hits and not live_pages
    return {
        "pass": passed,
        "close_call": close_call,
        "forbidden_hits": forbidden_hits,
        "live_pages": live_pages,
        "expectations": [
            {
                "text": "The transcript contains a family-correct browser CLOSE call after the "
                "last page it drove (suffix-matched: close_page/browser_close/stop_recording, or "
                "navigate_page to about:blank).",
                "passed": close_call is not None,
                "evidence": f"tool_use name={close_call!r}" if close_call else "no matching tool_use found",
            },
            {
                "text": "The transcript contains NO instance release/drop token "
                "(lease_release / lease_park tool call, allocator.py release / operation: drop / "
                "odoo_db.py drop).",
                "passed": not forbidden_hits,
                "evidence": (
                    "no forbidden token found"
                    if not forbidden_hits
                    else "; ".join(f"{h['token']!r} in {h['where']}" for h in forbidden_hits)
                ),
            },
            _live_pages_expectation(live_pages),
        ],
    }


# --------------------------------------------------------------------------------------------- #
# Eval B - visual-regression matrix close (odoo-visual-regression Round 4 / L1.7)
# --------------------------------------------------------------------------------------------- #

_NEW_PAGE_SUFFIX = "new_page"
_NAVIGATE_SUFFIX = "navigate_page"
_LIST_PAGES_SUFFIX = "list_pages"
_PAGE_LINE = re.compile(r"^\s*(\d+):\s*(\S+)", re.MULTILINE)


def _parse_list_pages(raw: str) -> tuple[list[int], list[str] | None]:
    """(open page ids, their URLs or None). Reads the fixture shape {"open_pages": [...]} and
    the server's own text ("1: about:blank [selected]", one line per page)."""
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return [int(i) for i in parsed.get("open_pages", [])], None
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    rows = _PAGE_LINE.findall(raw)
    if rows:
        return [int(i) for i, _url in rows], [url for _i, url in rows]
    return [int(n) for n in re.findall(r"\d+", raw)], None


def grade_eval_b(transcript_path) -> dict:
    """PASS iff the run ends with ONE page left, on about:blank, and the close step ran.

    chrome-devtools refuses to close its last page, so the contract's end state is "close every
    page but one, then navigate that one to about:blank" - a page REUSED by navigating is driven
    just like one opened with new_page. Ground truth, not the agent's claim:
      - the FINAL list_pages result shows at most one open page (and, when it reports URLs, that
        page is about:blank);
      - the LAST chrome-devtools navigation (new_page / navigate_page) went to about:blank, i.e.
        nothing was driven after the page was blanked;
      - list_pages was called at all.
      - every page driven by pageId was closed or ended on about:blank (`live_pages`).
    Each new_page this run issued mints the next page id (id 0 is the page the run found);
    `leftover_created_pages` lists those still open, as evidence.
    """
    id_by_tool_use_id: dict[str, str] = {}
    created_ids: set[int] = set()
    next_id = 1  # id 0 is the pre-existing/reused page
    last_list_pages_ids: list[int] | None = None
    last_list_pages_urls: list[str] | None = None
    list_pages_call_count = 0
    last_navigation_url: str | None = None
    navigations = 0

    for role, content in _iter_turns(transcript_path):
        for block in content:
            btype = block.get("type")
            if role == "assistant" and btype == "tool_use":
                name = str(block.get("name", ""))
                inp = block.get("input", {}) or {}
                tu_id = block.get("id")
                if tu_id:
                    id_by_tool_use_id[tu_id] = name
                if name.endswith(_NEW_PAGE_SUFFIX):
                    created_ids.add(next_id)
                    next_id += 1
                if name.endswith((_NEW_PAGE_SUFFIX, _NAVIGATE_SUFFIX)):
                    navigations += 1
                    url = inp.get("url") if isinstance(inp, dict) else None
                    last_navigation_url = str(url).strip() if url is not None else None
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
                last_list_pages_ids, last_list_pages_urls = _parse_list_pages(raw)

    leftover = sorted(created_ids.intersection(last_list_pages_ids or []))
    ran_at_all = last_list_pages_ids is not None
    one_page_left = ran_at_all and len(last_list_pages_ids) <= 1 and (
        last_list_pages_urls is None or all(u == _BLANK for u in last_list_pages_urls))
    live_pages, (last_drive_pid, _url) = _chrome_page_state(transcript_path)
    # A last navigation that names its page is judged per page (live_pages); only an unkeyed one
    # stands for "the page this run kept".
    blanked_last = navigations == 0 or last_drive_pid is not None or last_navigation_url == _BLANK
    passed = one_page_left and blanked_last and not live_pages

    return {
        "pass": passed,
        "created_pages": sorted(created_ids),
        "final_list_pages_open": last_list_pages_ids,
        "final_list_pages_urls": last_list_pages_urls,
        "leftover_created_pages": leftover,
        "list_pages_call_count": list_pages_call_count,
        "last_navigation_url": last_navigation_url,
        "live_pages": live_pages,
        "expectations": [
            {
                "text": "The final list_pages result shows at most one open page (every other "
                "page closed), and it is about:blank when the result names URLs.",
                "passed": one_page_left,
                "evidence": (
                    f"created={sorted(created_ids)} final_open={last_list_pages_ids} "
                    f"final_urls={last_list_pages_urls} leftover_created={leftover}"
                ),
            },
            {
                "text": "The matrix-shaped Round-4 close step actually fired (list_pages was "
                "called at least once).",
                "passed": list_pages_call_count > 0,
                "evidence": f"list_pages called {list_pages_call_count} time(s)",
            },
            {
                "text": "The last chrome-devtools navigation went to about:blank - nothing was "
                "driven after the kept page was blanked (judged per page when it names one).",
                "passed": blanked_last,
                "evidence": f"{navigations} navigation(s); last url={last_navigation_url!r}",
            },
            _live_pages_expectation(live_pages),
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
