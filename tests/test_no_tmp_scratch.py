"""Guard: the plugin writes NOTHING to `/tmp`, and its PR-review worktree lives beside the checkout.

Business rules protected here (two, sharing one scanner):

GT3b - **no scratch destination outside the state root.** `/tmp` is wiped on reboot, is
  shared by every user and every project on the host, and is not namespaced per
  project/worktree - so an artifact written there is both losable and un-attributable. The
  plugin's ONE sanctioned scratch/state destination is the Tier-1 state root
  (`snippets/state-root-resolution.md`), resolved by `odoo_ai_state_root`. Two rules enforce
  that, scanning every file under `plugins/` with whitespace normalized:

    Rule 1 - `TMPDIR` occurs ZERO times. Allowlist-free on purpose: the env var had exactly
      one occurrence in this repo's history and it WAS the leak (a per-invocation
      `mktemp "${TMPDIR:-/tmp}/odoo-spinup-XXXXXX"` conf that no exit path owned). A
      zero-tolerance count is the only bound that cannot be argued down one site at a time.

    Rule 2 - every `/tmp` (and `/var/tmp`) occurrence matches one of exactly two documented
      shapes: the state-root fallback `${HOME:-/tmp}` - a path-resolution last resort for a
      HOME-less environment, which writes nothing by itself - or an entry in `TMP_ALLOWLIST`,
      each carrying a reason. Anything else fails with its `file:line`.

  Rule 1 is also what makes the odoo-intake exemption clause's silence about `/tmp` PROVABLE
  rather than merely preferred: `test_odoo_intake_worktree_default.py` imports
  `tmpdir_hits_in_tree` from here instead of re-deriving the scan, so the prose criterion and
  the source fact are asserted against ONE mechanism.

GT4 - **the PR-review worktree is created beside the checkout, and is gitignored.** A git
  worktree under `/tmp` loses its checkout on a `/tmp` wipe while its `.git/worktrees/<name>`
  registration survives, and because the ISOLATE state key hashes the worktree's own
  top-level path, every review under a fresh `/tmp` path also minted a state tree nothing
  could ever reclaim. The replacement (`<repo-root>/.pr-worktrees/pr-<N>`) is stable per PR -
  but only safe if `.gitignore` covers it, because otherwise a review in progress makes
  `git status --porcelain` dirty, which `make gen-check` judges the whole tree by. That half
  is asserted BEHAVIOURALLY through `git check-ignore`, so the rule's spelling stays free.

Every text-matching helper below is a PURE FUNCTION of the text it is given, and each is
exercised against a MUST-CATCH / MUST-NOT-CATCH probe corpus in this same file. The probes are
the committed red-before-green proof: they are alternate SHAPES of the same defect, present
because a guard that recognises exactly one phrasing goes green while every other phrasing
walks past it.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from shutil import which

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = REPO_ROOT / "plugins"
CODE_REVIEW_SKILL = (
    PLUGINS_DIR / "odoo-ai-agents" / "skills" / "odoo-code-review" / "SKILL.md"
)

# Directories that are never source: build/VCS caches. Anything else under plugins/ is in
# scope, including docs, snippets, agents, skills, workflows and scripts - the claim-4
# regression this guards was PROSE telling an agent to write fragments under /tmp, not code.
_SKIP_DIR_PARTS = {"__pycache__", ".git", "node_modules", ".pytest_cache"}

# ---------------------------------------------------------------------------
# Rule 1 - TMPDIR
#
# Case-SENSITIVE, matching the environment variable's only real spelling: POSIX environment
# names are case-sensitive, so `$tmpdir` is a plain shell local and not this variable at all.
# `48-db-local-auth.sh` legitimately uses a local named `tmpdir` for a `mktemp -d` scratch dir
# it `rm -rf`s on every exit path - a bounded, owned directory, which is the opposite of the
# unowned destination this rule excludes.
#
# STATED BOUNDARY (so a reader does not over-trust this rule): a bare `mktemp`/`mktemp -d` with
# no argument still lands in the ambient temp dir without ever naming `TMPDIR`, and Rule 1
# cannot see that. Four such sites exist under plugins/ today (`48-db-local-auth.sh`,
# `20-browser-deps.sh`); all four remove what they create on every exit path, which is why they
# are not the defect this file guards. A NEW unremoved `mktemp` is not covered here - Rule 2
# catches it only if it also spells a `/tmp` literal.
# ---------------------------------------------------------------------------
TMPDIR_RE = re.compile(r"TMPDIR")

# ---------------------------------------------------------------------------
# Rule 2 - /tmp and /var/tmp
#
# The negative lookahead stops `/tmpfs`, `/tmpdirs` and friends from matching a bare `/tmp`
# prefix; `/var/tmp` is folded into the same pattern because it is the obvious workaround for
# a guard that only knows about `/tmp` (and is exactly as unsafe).
# ---------------------------------------------------------------------------
TMP_PATH_RE = re.compile(r"/(?:var/)?tmp(?![A-Za-z0-9_])")

# The ONE sanctioned shape: the state-root resolver's HOME-less last resort. It resolves a
# path, it does not write one, and `odoo_ai_state_root` is the only function allowed to spell
# it (see scripts/lib/state_reclaim.sh).
STATE_ROOT_FALLBACK_PREFIX = "${HOME:-"

# Explicit, reasoned exceptions. Keyed by path RELATIVE TO plugins/ plus the literal text, so
# an entry survives the file being re-ordered or re-wrapped (never a file:line pin).
TMP_ALLOWLIST: dict[str, list[tuple[str, str]]] = {
    "odoo-ai-agents/scripts/setup-steps/40-instance-profile.sh": [
        (
            "/tmp/profile.json",
            "user-facing copy telling a HUMAN where to hand-write a profile spec before "
            "invoking the step; no agent and no script ever writes this path, so it creates "
            "no artifact to reclaim",
        ),
    ],
}


def _normalize(line: str) -> str:
    """Collapse whitespace runs so a re-wrapped or re-indented site still matches."""
    return re.sub(r"\s+", " ", line)


def _iter_plugin_files():
    """Yield (relpath-under-plugins, text) for every readable text file under plugins/."""
    for path in sorted(PLUGINS_DIR.rglob("*")):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIR_PARTS for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary asset (icon/png) - carries no destination claim
        yield str(path.relative_to(PLUGINS_DIR)), text


def tmpdir_hits_in_text(text: str, relpath: str = "<text>") -> list[str]:
    """Every `TMPDIR` occurrence in `text`, as `relpath:lineno: <normalized line>`."""
    hits = []
    for lineno, line in enumerate(text.splitlines(), 1):
        normalized = _normalize(line)
        if TMPDIR_RE.search(normalized):
            hits.append(f"{relpath}:{lineno}: {normalized.strip()}")
    return hits


def unsanctioned_tmp_in_text(text: str, relpath: str = "<text>") -> list[str]:
    """Every `/tmp` or `/var/tmp` occurrence that matches NEITHER sanctioned shape."""
    allowed = TMP_ALLOWLIST.get(relpath, [])
    hits = []
    for lineno, line in enumerate(text.splitlines(), 1):
        normalized = _normalize(line)
        for match in TMP_PATH_RE.finditer(normalized):
            start = match.start()
            # Shape 1: the state-root fallback `${HOME:-/tmp}`.
            prefix_at = start - len(STATE_ROOT_FALLBACK_PREFIX)
            if prefix_at >= 0 and normalized[prefix_at:start] == STATE_ROOT_FALLBACK_PREFIX:
                continue
            # Shape 2: an allowlisted literal, matched by containment of THIS occurrence.
            if any(
                any(
                    occ <= start < occ + len(literal)
                    for occ in _all_indexes(normalized, literal)
                )
                for literal, _reason in allowed
            ):
                continue
            hits.append(f"{relpath}:{lineno}: {normalized.strip()}")
    return hits


def _all_indexes(haystack: str, needle: str) -> list[int]:
    out, start = [], haystack.find(needle)
    while start != -1:
        out.append(start)
        start = haystack.find(needle, start + 1)
    return out


def tmpdir_hits_in_tree() -> list[str]:
    """Rule 1 over the real tree. Imported by test_odoo_intake_worktree_default.py."""
    hits: list[str] = []
    for relpath, text in _iter_plugin_files():
        hits.extend(tmpdir_hits_in_text(text, relpath))
    return hits


def unsanctioned_tmp_in_tree() -> list[str]:
    """Rule 2 over the real tree."""
    hits: list[str] = []
    for relpath, text in _iter_plugin_files():
        hits.extend(unsanctioned_tmp_in_text(text, relpath))
    return hits


# ---------------------------------------------------------------------------
# Rule 1 / Rule 2 on the real tree
# ---------------------------------------------------------------------------


def test_plugin_tree_is_discovered():
    """Discovery floor: a scanner that walks nothing reports clean forever."""
    files = list(_iter_plugin_files())
    assert len(files) >= 200, (
        f"expected the plugins/ tree to yield a substantial file corpus, found {len(files)} - "
        f"a shrunken corpus means the two rules below are scanning almost nothing"
    )


def test_no_tmpdir_anywhere_under_plugins():
    """Rule 1 - an ambient temp-dir destination has no owner, so it may not be named at all.

    Zero, not "few": the single historical occurrence was the conf leak itself. Any
    reintroduction - `${TMPDIR:-/tmp}`, `os.environ["TMPDIR"]`, `TMPDIR=` in a hook, or prose
    telling an agent to honour `$TMPDIR` - is a regression of the same defect.
    """
    hits = tmpdir_hits_in_tree()
    assert hits == [], (
        "TMPDIR must not appear anywhere under plugins/: an ambient temp dir is not "
        "namespaced per project/worktree and nothing reclaims what lands there. Write to the "
        "Tier-1 state root via odoo_ai_state_root (scripts/lib/state_reclaim.sh) instead.\n"
        + "\n".join(hits)
    )


def test_every_tmp_occurrence_under_plugins_matches_a_documented_shape():
    """Rule 2 - `/tmp` and `/var/tmp` survive only as the state-root fallback or a reasoned entry."""
    hits = unsanctioned_tmp_in_tree()
    assert hits == [], (
        "Every /tmp (or /var/tmp) occurrence under plugins/ must be either the state-root "
        "fallback shape ${HOME:-/tmp} (path resolution, writes nothing) or an entry in "
        "TMP_ALLOWLIST with a stated reason. Unsanctioned occurrences:\n" + "\n".join(hits)
    )


def test_state_root_fallback_shape_still_exists_and_is_the_sanctioned_one():
    """The MUST-NOT-CATCH control, asserted on the tree rather than only on a probe.

    `${HOME:-/tmp}/.odoo-ai` is a CORRECT resolution and must never fail Rule 2. It is
    asserted as a SHAPE wherever it appears, deliberately not as a count of sites: the
    reclamation work collapsed the previously duplicated expression into one resolver, so any
    guard pinned to a site count would be false the day it landed - and would also punish the
    next legitimate de-duplication.
    """
    shaped = [
        relpath
        for relpath, text in _iter_plugin_files()
        if STATE_ROOT_FALLBACK_PREFIX + "/tmp}" in re.sub(r"\s+", " ", text)
    ]
    assert shaped, (
        "the state-root fallback shape ${HOME:-/tmp} vanished from plugins/ entirely - the "
        "resolver must still resolve a path in a HOME-less environment; if this moved, point "
        "this guard at wherever it moved to rather than deleting it"
    )
    for relpath in shaped:
        text = (PLUGINS_DIR / relpath).read_text(encoding="utf-8")
        assert unsanctioned_tmp_in_text(text, relpath) == [], (
            f"{relpath} spells the sanctioned state-root fallback but Rule 2 flagged it - "
            f"Rule 2 has become over-strict and now fails compliant code"
        )


def test_allowlist_entries_are_reasoned_and_still_needed():
    """An allowlist that outlives its entries is how an exception becomes the rule."""
    for relpath, entries in TMP_ALLOWLIST.items():
        path = PLUGINS_DIR / relpath
        assert path.is_file(), (
            f"TMP_ALLOWLIST names {relpath}, which no longer exists - drop the stale entry"
        )
        text = re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))
        for literal, reason in entries:
            assert literal in text, (
                f"TMP_ALLOWLIST exempts {literal!r} in {relpath}, but that literal is gone - "
                f"drop the entry instead of leaving a standing exemption"
            )
            assert len(reason.split()) >= 8, (
                f"the allowlist entry for {literal!r} in {relpath} needs a real reason, not a "
                f"label - got {reason!r}"
            )


# ---------------------------------------------------------------------------
# Rule 1 / Rule 2 probe corpus - the committed red-before-green proof.
#
# MUST-CATCH: each is a DIFFERENT shape of the same defect. MUST-NOT-CATCH: each is compliant
# text the rule must leave alone.
# ---------------------------------------------------------------------------

TMPDIR_MUST_CATCH = [
    ('shell env default', 'conf="$(mktemp "${TMPDIR:-/tmp}/odoo-spinup-XXXXXX")"'),
    ('python env read', 'base = os.environ["TMPDIR"]'),
    ('python env get', 'base = os.environ.get("TMPDIR", "/var/tmp")'),
    ('bare shell expansion', 'logf="$TMPDIR/run.log"'),
    ('assignment in a hook', 'TMPDIR=/tmp/odoo-ai exec "$@"'),
    ('prose instruction', 'Write the fragment under `$TMPDIR` so it is cleaned up for you.'),
    ('wrapped across whitespace', 'export    TMPDIR="$HOME/scratch"'),
]

TMPDIR_MUST_NOT_CATCH = [
    ('state root resolver', 'printf \'%s\\n\' "${ODOO_AI_HOME:-${HOME:-/tmp}/.odoo-ai}"'),
    ('pytest fixture name', 'farm = tmp_path_factory.mktemp("path_farm")'),
    ('temp word in prose', 'The generated conf is no longer a temp file.'),
    # A shell local named `tmpdir`, removed on every exit path, is an OWNED scratch dir - not
    # the ambient env-var destination Rule 1 excludes (see the STATED BOUNDARY above).
    ('owned shell-local scratch dir', 'tmpdir="$(mktemp -d)"; cur="$tmpdir/cur"'),
]

TMP_MUST_CATCH = [
    ('shell mkdir', 'mkdir -p /tmp/odoo-ai-scratch'),
    ('shell log path', 'logf="/tmp/run.log"'),
    ('python path join', 'target = Path("/tmp") / slug'),
    ('prose telling an agent to write there', 'Write log fragments to `/tmp/<db>.log` as you go.'),
    ('var/tmp workaround', 'mkdir -p /var/tmp/odoo-ai-scratch'),
    ('pr worktree', 'Create the review worktree at /tmp/pr-review-<N>.'),
    ('tmpdir default expansion', 'conf="${TMPDIR:-/tmp}/odoo.conf"'),
]

TMP_MUST_NOT_CATCH = [
    ('state root fallback', 'printf \'%s\\n\' "${ODOO_AI_HOME:-${HOME:-/tmp}/.odoo-ai}"'),
    ('state root fallback in prose', 'The `${HOME:-/tmp}` inner default is a last resort.'),
    ('tmpfs is a different path', 'mount -t tmpfs none /tmpfs-mount'),
    ('no tmp at all', 'conf="$(odoo_ai_state_root)/conf/${db_name}-${port}.conf"'),
]


@pytest.mark.parametrize("shape,line", TMPDIR_MUST_CATCH, ids=[s for s, _ in TMPDIR_MUST_CATCH])
def test_rule1_catches_every_tmpdir_shape(shape, line):
    assert tmpdir_hits_in_text(line, "probe.sh"), (
        f"Rule 1 let a {shape} shape through: {line!r}. A guard that recognises one spelling "
        f"of an ambient temp dir and misses the rest protects nothing."
    )


@pytest.mark.parametrize(
    "shape,line", TMPDIR_MUST_NOT_CATCH, ids=[s for s, _ in TMPDIR_MUST_NOT_CATCH]
)
def test_rule1_leaves_compliant_text_alone(shape, line):
    assert tmpdir_hits_in_text(line, "probe.sh") == [], (
        f"Rule 1 fired on compliant text ({shape}): {line!r}"
    )


@pytest.mark.parametrize("shape,line", TMP_MUST_CATCH, ids=[s for s, _ in TMP_MUST_CATCH])
def test_rule2_catches_every_tmp_destination_shape(shape, line):
    assert unsanctioned_tmp_in_text(line, "probe.sh"), (
        f"Rule 2 let a {shape} shape through: {line!r}. Prose counts: the pattern this guards "
        f"was legitimised by documentation, not only by code."
    )


@pytest.mark.parametrize("shape,line", TMP_MUST_NOT_CATCH, ids=[s for s, _ in TMP_MUST_NOT_CATCH])
def test_rule2_leaves_compliant_text_alone(shape, line):
    assert unsanctioned_tmp_in_text(line, "probe.sh") == [], (
        f"Rule 2 fired on compliant text ({shape}): {line!r}"
    )


def test_rule2_allowlist_is_scoped_to_the_file_that_earned_it():
    """An allowlist entry must not become a global escape hatch."""
    owner = "odoo-ai-agents/scripts/setup-steps/40-instance-profile.sh"
    line = "        echo \"       ODOO_AI_PROFILE_SPEC=/tmp/profile.json bash $0 apply\" >&2"
    assert unsanctioned_tmp_in_text(line, owner) == [], (
        "the allowlisted user-facing example must pass in its own file"
    )
    assert unsanctioned_tmp_in_text(line, "odoo-ai-agents/skills/odoo-intake/SKILL.md"), (
        "the SAME literal in a DIFFERENT file must still fail - an allowlist keyed on the "
        "literal alone would let any file adopt the exemption"
    )


# ---------------------------------------------------------------------------
# GT4 - the PR-review worktree location
# ---------------------------------------------------------------------------

# Synonyms for the S9 invariant, so a re-wording of the clause cannot break the guard while
# a DELETION of it still does.
_MAIN_CHECKOUT_CRITERION = re.compile(
    r"never\s+(?:in\s+)?the\s+main\s+checkout"
    r"|not\s+the\s+main\s+checkout"
    r"|never\s+the\s+principal\s+checkout",
    re.IGNORECASE,
)
_BLOCK_BOUNDARY = re.compile(r"^(?:\*\*|#{1,6}\s)")


def pr_target_blocks(text: str) -> list[str]:
    """Every block of `text` whose opening line mentions a `TARGET=pr:` resolution.

    A block runs from its opening line to the next bold-paragraph or heading line, so the
    numbered steps that belong to a `**Pre-resolution ...**` paragraph travel with it. Located
    by CONTENT, never by line number, so the step may move within the file.
    """
    lines = text.splitlines()
    blocks = []
    for idx, line in enumerate(lines):
        if "TARGET=pr:" not in line:
            continue
        end = idx + 1
        while end < len(lines) and not _BLOCK_BOUNDARY.match(lines[end]):
            end += 1
        blocks.append("\n".join(lines[idx:end]))
    return blocks


def pr_worktree_blocks(text: str) -> list[str]:
    """The `TARGET=pr:` blocks that actually resolve a worktree (the ones GT4 is about)."""
    return [b for b in pr_target_blocks(text) if "worktree" in b.lower()]


def test_pr_review_resolves_a_worktree_beside_the_checkout_not_in_tmp():
    """GT4(1) - the `pr:` pre-resolution names a `.pr-worktrees/pr-<N>` path, never a temp one.

    `.pr-worktrees/` sits beside the checkout, so it survives a reboot and hashes to a STABLE
    ISOLATE key per PR (a fresh temp path minted a new, unreclaimable state tree per review).
    """
    text = CODE_REVIEW_SKILL.read_text(encoding="utf-8")
    blocks = pr_worktree_blocks(text)
    assert blocks, (
        "odoo-code-review/SKILL.md must resolve TARGET=pr:<N> to an isolated WORKTREE - no "
        "TARGET=pr: step mentioning a worktree was found at all"
    )
    joined = "\n".join(blocks)
    assert re.search(r"\.pr-worktrees/pr-", joined), (
        "the PR-review worktree must live at <repo-root>/.pr-worktrees/pr-<N> - a path keyed "
        f"per PR beside the checkout. Block(s) found:\n{joined}"
    )
    assert unsanctioned_tmp_in_text(joined, "<pr-preresolution-block>") == [], (
        "the PR-review worktree must not be placed under /tmp or /var/tmp (Rule 2 above is "
        f"the SSOT for why). Block(s) found:\n{joined}"
    )
    assert "show-toplevel" not in joined, (
        "the pr: pre-resolution must NOT resolve review_root from `git rev-parse "
        "--show-toplevel` - that is the main checkout, which S9 forbids as a review target"
    )


def test_pr_review_keeps_the_never_the_main_checkout_invariant():
    """GT4(3) - relocating the worktree must not quietly drop the S9 clause that names WHY."""
    text = CODE_REVIEW_SKILL.read_text(encoding="utf-8")
    joined = "\n".join(pr_worktree_blocks(text))
    assert "S9" in joined, (
        "the pr: worktree step must still cite S9 (git-delegation.md's never-the-main-checkout "
        f"invariant). Block(s) found:\n{joined}"
    )
    assert _MAIN_CHECKOUT_CRITERION.search(joined), (
        "the pr: worktree step must still state the S9 CRITERION (never the main checkout), "
        f"not merely cite the label. Block(s) found:\n{joined}"
    )


@pytest.mark.skipif(which("git") is None, reason="git not available")
def test_pr_worktrees_directory_is_gitignored():
    """GT4(2) - asserted through git itself, so `.gitignore`'s exact spelling stays free.

    This is the silent half: a `.pr-worktrees/` checkout that git does NOT ignore turns every
    PR review into a dirty `git status --porcelain`, which `make gen-check` (and CI) judges the
    whole tree by - so the relocation would pass review and then break every later PR.
    """
    res = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "check-ignore", "-q", ".pr-worktrees/pr-1"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, (
        "git does not ignore .pr-worktrees/pr-1 - add a rule covering .pr-worktrees/ to "
        f".gitignore (check-ignore exit {res.returncode}: {res.stderr.strip()})"
    )


# ---------------------------------------------------------------------------
# GT4 probe corpus - the block extractor must catch every relocation shape.
# ---------------------------------------------------------------------------

_PR_BLOCK_TEMPLATE = (
    "**Pre-resolution for `TARGET=pr:<N>`** - resolve the PR to an isolated worktree:\n"
    "1. Invoke `git-toolkit:git-ops` to fetch PR metadata.\n"
    "2. Invoke `git-toolkit:git-ops` to create an isolated worktree ({path}, S9 - never the "
    "main checkout) with the PR branch checked out; receive `review_root`.\n"
    "\n"
    "**Resolve the review's state dirs ONCE** against `review_root`.\n"
)

PR_PATH_MUST_CATCH = [
    ("reverted to tmp", "`/tmp/pr-review-<N>`"),
    ("moved to var/tmp", "`/var/tmp/pr-review-<N>`"),
    ("tmpdir env", "`$TMPDIR/pr-review-<N>`"),
    ("main checkout via show-toplevel", "`$(git rev-parse --show-toplevel)`"),
]

PR_PATH_MUST_NOT_CATCH = [
    ("relative", "`.pr-worktrees/pr-<N>`"),
    ("absolute repo-root form", "`<repo-root>/.pr-worktrees/pr-<N>`"),
    ("shell-resolved repo root", "`${REPO_ROOT}/.pr-worktrees/pr-<N>`"),
]


def _pr_path_verdict(path: str) -> bool:
    """True when the GT4(1) assertions accept `path`; mirrors the real test's checks."""
    blocks = pr_worktree_blocks(_PR_BLOCK_TEMPLATE.format(path=path))
    if not blocks:
        return False
    joined = "\n".join(blocks)
    return bool(
        re.search(r"\.pr-worktrees/pr-", joined)
        and unsanctioned_tmp_in_text(joined, "<probe>") == []
        and "show-toplevel" not in joined
    )


@pytest.mark.parametrize("shape,path", PR_PATH_MUST_CATCH, ids=[s for s, _ in PR_PATH_MUST_CATCH])
def test_gt4_rejects_every_relocation_shape(shape, path):
    assert not _pr_path_verdict(path), (
        f"GT4 accepted a {shape} PR-worktree path ({path}) - each of these reintroduces either "
        f"the /tmp-wipe hazard or the S9 main-checkout violation"
    )


@pytest.mark.parametrize(
    "shape,path", PR_PATH_MUST_NOT_CATCH, ids=[s for s, _ in PR_PATH_MUST_NOT_CATCH]
)
def test_gt4_accepts_every_compliant_spelling(shape, path):
    assert _pr_path_verdict(path), (
        f"GT4 rejected a compliant {shape} PR-worktree path ({path}) - the guard must key on "
        f"the .pr-worktrees/pr-<N> location, not on one way of writing the repo root"
    )


def test_gt4_block_extractor_ignores_unrelated_target_kinds():
    """MUST-NOT-CATCH control on the extractor itself: only `pr:` blocks are in scope."""
    text = (
        "- `TARGET=local` -> `review_root` = `git rev-parse --show-toplevel`.\n"
        "- `TARGET=worktree:<abs-path>` -> `review_root` = `<abs-path>`.\n"
    )
    assert pr_target_blocks(text) == [], (
        "the extractor must not pick up TARGET=local / TARGET=worktree steps - `show-toplevel` "
        "is CORRECT for TARGET=local and must never be flagged there"
    )
