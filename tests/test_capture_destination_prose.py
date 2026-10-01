"""Prose guard: no instruction anywhere in the plugin can route a capture outside the state root,
frame a doc image by a non-existent parameter, or link a module doc to a path the store cannot
serve.

The rules these phrases contradict live in their SSOTs:

- every capture names an ABSOLUTE path under `<ISOLATE_DIR>` / `<SHARE_DIR>` -
  `snippets/state-root-resolution.md` § Where a captured artifact goes;
- doc images are framed for their placement slot - `skills/odoo-doc-illustration/references/
  capture-mechanics.md` § Frame for the placement slot;
- module-doc references and cross-module links - `snippets/module-doc-references.md`.

A superseded instruction left anywhere in the tree is read by some agent and acted on, so the scan
covers the WHOLE plugin tree (Markdown, YAML, JSON, shell), never a hand-picked file list. Text is
whitespace-normalized (and line-leading comment markers dropped) before matching, so a soft line
wrap or a YAML/shell comment prefix cannot hide a phrase. Excluded: CHANGELOG (history, never
read as an instruction) and `evals/` fixtures (test prompts, not agent-facing prose).

Every matcher is also exercised against planted positive and negative strings, so each check is
proven able to fail.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"

SCANNED_SUFFIXES = {".md", ".yaml", ".yml", ".json", ".sh"}

# The only files allowed to spell a pattern, each because it is the SSOT stating the ban (or the
# runtime code that owns the setting). Every entry is checked to exist.
MODULE_DOC_SSOT = "snippets/module-doc-references.md"
RECORDING_DIR_OWNERS = {
    "scripts/lib/browser_mcp_servers.py",
    "scripts/mcp/browser_mcp_launch.py",
}


def _rel(path: Path) -> str:
    return path.relative_to(PLUGIN).as_posix()


def _excluded(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return name.upper().startswith("CHANGELOG") or "/evals/" in f"/{rel}"


def _files(suffixes: set[str]) -> list[Path]:
    return sorted(
        p for p in PLUGIN.rglob("*")
        if p.is_file() and p.suffix in suffixes and not _excluded(_rel(p))
    )


_COMMENT_LEAD_RE = re.compile(r"^[ \t]*(?:#+|>+|//)[ \t]?", re.M)


def _normalize(text: str) -> str:
    return " ".join(_COMMENT_LEAD_RE.sub("", text).split())


SCANNED = _files(SCANNED_SUFFIXES)
NORMALIZED = {_rel(p): _normalize(p.read_text(encoding="utf-8", errors="replace")) for p in SCANNED}


# --------------------------------------------------------------------------- #
# Matchers - each returns the offending snippets found in normalized text
# --------------------------------------------------------------------------- #
def _hits(regex: re.Pattern[str], text: str) -> list[str]:
    return [text[max(0, m.start() - 40): m.end() + 40] for m in regex.finditer(text)]


# A cwd-relative capture tree, or an instruction to pass a relative capture filename.
PLAYWRIGHT_CWD_RE = re.compile(r"\.playwright-mcp")
RELATIVE_FILENAME_RE = re.compile(r"relative\s+`?(?:file)?name`?\b|relative\s+`?filePath`?", re.I)
BRANCH_RE = re.compile(r"\bBranch [AB]\b")
SMALLEST_REGION_RE = re.compile(r"smallest\s+region", re.I)
CLIP_PARAM_RE = re.compile(r"`clip`|\bclip\s+rect\b|\bclip\s*[:=]", re.I)
ANNOTATED_RE = re.compile(r"annotated\s+screenshots?", re.I)
RECORDINGS_CWD_RE = re.compile(r"\./recordings\b")
RECORDING_DIR_RE = re.compile(r"RECORDING_OUTPUT_DIR")
STORE_ABSOLUTE_RE = re.compile(r"https?://[^\s)\"'`<>]*/apps/modules/", re.I)
SIBLING_MODULE_RE = re.compile(
    r"\.\./\.\./(?:<[^>\s]+>|&lt;[^&\s]+&gt;|[a-z_][a-z0-9_]*/(?:static|doc)/)"
)

_TWO_TIER_RE = re.compile(r"two-tier", re.I)
_CAPTURE_WORD_RE = re.compile(
    r"capture|screenshot|playwright|pagecast|staging|filename|filePath|recording|cwd", re.I
)


def _two_tier_capture_hits(text: str) -> list[str]:
    """`two-tier` used for a capture write (stage relative, then copy). The plugin uses
    "two-tier" legitimately elsewhere (work-item decomposition, worktree topology, SSOT tiers),
    so a hit needs capture vocabulary in the same window - scope by meaning, not adjacency."""
    out = []
    for m in _TWO_TIER_RE.finditer(text):
        window = text[max(0, m.start() - 160): m.end() + 160]
        if _CAPTURE_WORD_RE.search(window):
            out.append(window)
    return out


# A capture tool's destination argument whose example value is a path not rooted at the state
# root. Only path-shaped values count (a `/` or a file extension), so "`filename` = the absolute
# path" (a description, not a value) is not a hit. `filePath` / `outputDirPath` / `webmPath` are
# capture-only keys in any spelling; `filename` is also an ordinary English word and a CLI flag
# suffix (`--export-filename=`), so it counts only in parameter form - code-quoted or JSON-quoted.
_CAPTURE_KEY_ARG_RE = re.compile(
    r"(?<![\w-])([`\"']?)(filePath|filename|outputDirPath|webmPath)\b([`\"']?)\s*[:=]\s*[`\"']?"
    r"([^\s`\"',)}]+)"
)
_PATHISH_RE = re.compile(r"/|\.\w{2,4}$")
_ROOTED = ("<ISOLATE_DIR>", "<SHARE_DIR>")


def _unrooted_capture_args(text: str) -> list[str]:
    out = []
    for m in _CAPTURE_KEY_ARG_RE.finditer(text):
        open_q, key, close_q, value = m.groups()
        if key == "filename" and not (open_q or close_q):
            continue
        if _PATHISH_RE.search(value) and not value.startswith(_ROOTED):
            out.append(m.group(0))
    return out


SIMPLE_RULES: dict[str, tuple[re.Pattern[str], str, set[str]]] = {
    "playwright-cwd-tree": (
        PLAYWRIGHT_CWD_RE, "captures go under <ISOLATE_DIR>/<SHARE_DIR>, never a cwd tree", set()),
    "relative-filename": (
        RELATIVE_FILENAME_RE, "every capture names an ABSOLUTE path (state-root-resolution.md)", set()),
    "branch-a-b": (BRANCH_RE, "the cwd write branches were removed with the relative capture path", set()),
    "smallest-region": (
        SMALLEST_REGION_RE, "frame for the placement slot (capture-mechanics.md section 7)", set()),
    "clip-parameter": (CLIP_PARAM_RE, "playwright has no `clip` screenshot parameter", set()),
    "annotated-screenshot": (ANNOTATED_RE, "doc and marketing images are never annotated", set()),
    "pagecast-cwd-recordings": (
        RECORDINGS_CWD_RE, "pagecast output is moved into <ISOLATE_DIR>, never left in ./recordings", set()),
    "store-absolute-url": (
        STORE_ABSOLUTE_RE, "cross-module links are root-relative /apps/modules/<series>/<module>", set()),
    "sibling-module-path": (
        SIBLING_MODULE_RE, "a sibling module path does not exist on the store", {MODULE_DOC_SSOT}),
}


# --------------------------------------------------------------------------- #
# Proof each matcher can fail (planted strings, not the tree)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "rule, bad, good",
    [
        ("playwright-cwd-tree", "stage under .playwright-mcp/<run_id>/", "stage under <ISOLATE_DIR>/visual/"),
        ("relative-filename", "playwright REQUIRES a RELATIVE `filename` under its root",
         "pass the absolute path as `filename`"),
        ("relative-filename", "use a relative filename", "use an absolute filename"),
        ("branch-a-b", "Branch A (dest inside cwd): write directly", "branch A->{B,C} (2 inst)"),
        ("smallest-region", "capture the smallest region that shows it", "capture the slot"),
        ("clip-parameter", "browser_take_screenshot with a `clip` rect", "a demo clip of the flow"),
        ("annotated-screenshot", "annotated screenshots of the flow", "screenshots of the flow"),
        ("pagecast-cwd-recordings", "files land in ./recordings by default", "files land in <ISOLATE_DIR>"),
        ("store-absolute-url", "https://apps.example.com/apps/modules/17.0/sale",
         "/apps/modules/<odoo_version>/sale"),
        ("sibling-module-path", "see ../../<base>/doc/index.rst", "see ../../LICENSE"),
        ("sibling-module-path", "see ../../sale/static/description/x.png", "see ../static/description/x.png"),
    ],
)
def test_matcher_can_fail(rule: str, bad: str, good: str):
    regex = SIMPLE_RULES[rule][0]
    assert _hits(regex, _normalize(bad)), f"{rule} must flag: {bad!r}"
    assert not _hits(regex, _normalize(good)), f"{rule} must pass: {good!r}"


def test_normalization_defeats_line_wrap_and_comment_prefix():
    wrapped = "playwright REQUIRES a RELATIVE\n    #   `filename` under its output root"
    assert _hits(RELATIVE_FILENAME_RE, _normalize(wrapped))


def test_two_tier_matcher_is_scoped_to_capture_sense():
    assert _two_tier_capture_hits(_normalize("so it keeps the two-tier write into .playwright staging"))
    assert not _two_tier_capture_hits(_normalize("## Two-tier decomposition axis - work items per node"))


def test_unrooted_capture_arg_matcher_can_fail():
    assert _unrooted_capture_args("`filePath: /tmp/shot.png`")
    assert _unrooted_capture_args('"filename": "shot.png"')
    assert _unrooted_capture_args("webmPath=./recordings/x.webm")
    assert not _unrooted_capture_args("`filePath: <ISOLATE_DIR>/visual/debug/<slug>/s.png`")
    assert not _unrooted_capture_args("`outputDirPath: <SHARE_DIR>/visual/baselines/`")
    assert _unrooted_capture_args("`filename`: `shots/x.png`")
    assert not _unrooted_capture_args("`filename` = the absolute path")
    assert not _unrooted_capture_args("--export-filename=icon.png icon.svg")
    assert not _unrooted_capture_args("Per-step filename: `<scenario-slug>-step<NN>.png`")


def test_recording_dir_matcher_can_fail():
    assert RECORDING_DIR_RE.search("set RECORDING_OUTPUT_DIR yourself")
    assert not RECORDING_DIR_RE.search("pagecast writes where the launcher points it")


# --------------------------------------------------------------------------- #
# The tree scan
# --------------------------------------------------------------------------- #
def test_scan_is_not_vacuous():
    rels = set(NORMALIZED)
    assert len(rels) > 200, f"scan found only {len(rels)} files - the walk or the filter broke"
    for must in (
        "snippets/state-root-resolution.md",
        "skills/odoo-doc-illustration/references/capture-mechanics.md",
        "workflows/video-produce.workflow.yaml",
        "hooks/hooks.json",
        "scripts/setup-steps/12-browser-mcp-optin.sh",
    ):
        assert must in rels, f"{must} must be in the scan universe"


def test_allowlisted_files_exist():
    for rel in {MODULE_DOC_SSOT} | RECORDING_DIR_OWNERS:
        assert (PLUGIN / rel).is_file(), f"allowlist entry has no file: {rel}"


@pytest.mark.parametrize("rule", sorted(SIMPLE_RULES))
def test_no_superseded_capture_or_reference_instruction(rule: str):
    regex, why, allowed = SIMPLE_RULES[rule]
    offenders = {
        rel: hits for rel, text in NORMALIZED.items()
        if rel not in allowed and (hits := _hits(regex, text))
    }
    assert not offenders, f"[{rule}] {why}; found: {offenders}"


def test_no_two_tier_capture_write():
    offenders = {rel: h for rel, text in NORMALIZED.items() if (h := _two_tier_capture_hits(text))}
    assert not offenders, f"captures are written once, absolute, under the state root; found: {offenders}"


def test_every_capture_path_example_is_rooted_at_the_state_root():
    offenders = {rel: h for rel, text in NORMALIZED.items() if (h := _unrooted_capture_args(text))}
    assert not offenders, (
        "a capture tool's destination example must start with <ISOLATE_DIR> or <SHARE_DIR>; "
        f"found: {offenders}"
    )


def test_recording_output_dir_is_set_only_by_its_owners():
    """Only the launcher (via the server SSOT) sets pagecast's output dir; prose that tells an
    agent to set or rely on it would bypass the launcher."""
    universe = _files(SCANNED_SUFFIXES | {".py"})
    offenders = [
        _rel(p) for p in universe
        if _rel(p) not in RECORDING_DIR_OWNERS
        and RECORDING_DIR_RE.search(p.read_text(encoding="utf-8", errors="replace"))
    ]
    assert not offenders, f"RECORDING_OUTPUT_DIR outside its owners: {offenders}"
