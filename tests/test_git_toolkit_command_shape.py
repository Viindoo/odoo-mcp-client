"""Guard: every command git-toolkit shows an agent is one plain call (S12 - Command shape).

Business rule: a git-toolkit agent copies the commands its prose shows. A subagent's Bash working
directory resets between calls and a permission layer judges each call by its literal text, so a
compound line (`a && b`, `x | grep`, `$(...)`, a leading `VAR=value`, `-c key=value`, `cd`) is
refused or misjudged at run time even though it reads fine on the page. S12 in
`plugins/git-toolkit/snippets/git-safety-contract.md` states the shape; this test keeps every
fenced shell block under `plugins/git-toolkit/` in that shape, keeps the one editor override where
S12 allows it, keeps `git stash` and a hard-coded `commit -s` out of the recipes (S4 never
stashes; C4 signs off only when required), and keeps every git-toolkit agent pointing at S12. It also keeps S13 (a new branch has no upstream
until its first push): every recipe that creates a branch says `--no-track`, and every recipe push
names its remote and branch, so a branch cut from `origin/<series>` can never push to that series
by default.

The detector is a pure function of one command line, proved against a MUST-CATCH probe list of
the shapes the recipes used to show and a MUST-NOT-CATCH list of legal lines that look similar.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLKIT = REPO_ROOT / "plugins" / "git-toolkit"
SAFETY_CONTRACT = TOOLKIT / "snippets" / "git-safety-contract.md"

SHELL_LANGS = {"bash", "sh", "shell", "console", "zsh"}

# The one bare push the prose shows: S2's BANNED example.
BANNED_FORCE_PUSH = "git push --force"

# The ONE editor override S12 allows, spelled exactly.
EDITOR_EXCEPTION = "GIT_EDITOR=true GIT_SEQUENCE_EDITOR=true git -C <worktree> rebase <args>"

_FENCE_RE = re.compile(r"^(\s*)```+\s*([A-Za-z0-9_-]*)\s*$")
_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_GLOBAL_C_RE = re.compile(r"^git(?:\s+-C\s+(?:<[^>]*>|\S+))*\s+-c(?:\s|$)")
_EDITOR_VAR_RE = re.compile(r"\b(?:GIT_EDITOR|GIT_SEQUENCE_EDITOR|EDITOR|VISUAL)=")
_STASH_RE = re.compile(r"\bgit(?:\s+-C\s+(?:<[^>]*>|\S+))*\s+stash\b")
_COMMIT_SIGNOFF_RE = re.compile(r"\bcommit\b(?:\s+\S+)*?\s-s\b")


def _strip_comment(line: str) -> str:
    """Drop a shell comment (`#` at line start or after whitespace, outside quotes)."""
    quote = ""
    prev = " "
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "#" and prev.isspace():
            return line[:i].rstrip()
        prev = ch
    return line.rstrip()


def _unquoted(line: str) -> str:
    """The line with single-quoted spans blanked (they are literal to the shell)."""
    out = []
    in_single = False
    for ch in line:
        if ch == "'":
            in_single = not in_single
            out.append(" ")
        else:
            out.append(" " if in_single else ch)
    return "".join(out)


def _outside_all_quotes(line: str) -> str:
    out = []
    quote = ""
    for ch in line:
        if quote:
            if ch == quote:
                quote = ""
            out.append(" ")
        elif ch in ("'", '"'):
            quote = ch
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def shape_violations(command: str) -> list[str]:
    """Return why one command line is not a plain S12 call ([] when it is)."""
    cmd = command.strip()
    if not cmd:
        return []
    problems: list[str] = []
    bare = _outside_all_quotes(cmd)
    for token, name in (("&&", "&&"), ("||", "||"), (";", ";"), ("|", "pipe")):
        if token in bare:
            problems.append(name)
    no_single = _unquoted(cmd)
    if "$(" in no_single:
        problems.append("$(...)")
    if "`" in no_single:
        problems.append("backtick")
    if _ASSIGN_RE.match(cmd) and cmd != EDITOR_EXCEPTION:
        problems.append("leading VAR=value")
    if _GLOBAL_C_RE.match(cmd):
        problems.append("global -c")
    if cmd == "cd" or cmd.startswith("cd "):
        problems.append("cd")
    # A pipe check above already covers `||`; drop the duplicate pipe report for it.
    if "||" in problems and "pipe" in problems and "|" not in bare.replace("||", ""):
        problems.remove("pipe")
    return problems


def _fenced_commands(path: Path) -> list[tuple[int, str]]:
    """Every command line of every fenced shell block, comments stripped, continuations joined."""
    commands: list[tuple[int, str]] = []
    in_fence = False
    is_shell = False
    pending = ""
    pending_line = 0
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = _FENCE_RE.match(raw)
        if match:
            if not in_fence:
                in_fence = True
                is_shell = match.group(2).lower() in SHELL_LANGS
            else:
                in_fence = False
                is_shell = False
            continue
        if not (in_fence and is_shell):
            continue
        text = _strip_comment(raw.strip())
        if text.endswith("\\"):
            if not pending:
                pending_line = lineno
            pending += text[:-1] + " "
            continue
        if pending:
            text = pending + text
            lineno = pending_line
            pending = ""
        text = " ".join(text.split())
        if text:
            commands.append((lineno, text))
    return commands


_INLINE_SPAN_RE = re.compile(r"`([^`]+)`")
_GLOBAL_PATH_RE = re.compile(r"^git((?:\s+-C\s+\S+)*)\s+")
# `git branch` flags that do not create a branch.
_BRANCH_NON_CREATING = {
    "-d", "-D", "--delete", "-m", "-M", "--move", "-c", "-C", "--copy", "-l", "--list",
    "--show-current", "-a", "--all", "-r", "--remotes", "-v", "-vv", "--verbose", "--contains",
    "--no-contains", "--merged", "--no-merged", "--points-at", "--edit-description",
    "-u", "--set-upstream-to", "--unset-upstream",
}


def _subcommand_tokens(command: str) -> list[str]:
    """Tokens after `git` and any `-C <path>` globals; [] when the line is not a git call."""
    cmd = " ".join(command.split())
    match = _GLOBAL_PATH_RE.match(cmd)
    if not match:
        return []
    return cmd[match.end():].split()


def creates_branch_without_no_track(command: str) -> bool:
    """True when one git call creates a NEW branch and does not say `--no-track` (S13)."""
    tokens = _subcommand_tokens(command)
    if not tokens:
        return False
    sub, args = tokens[0], tokens[1:]
    if sub == "worktree":
        creates = bool(args) and args[0] == "add" and any(a in ("-b", "-B") for a in args)
    elif sub == "checkout":
        creates = any(a in ("-b", "-B") for a in args)
    elif sub == "switch":
        creates = any(a in ("-c", "-C", "--create", "--force-create") for a in args)
    elif sub == "branch":
        creates = (
            any(not a.startswith("-") for a in args)
            and not any(a in _BRANCH_NON_CREATING for a in args)
        )
    else:
        creates = False
    return creates and "--no-track" not in args


def push_without_remote_and_branch(command: str) -> bool:
    """True when one `git push` call does not name both its remote and what it pushes (S13)."""
    tokens = _subcommand_tokens(command)
    if not tokens or tokens[0] != "push":
        return False
    if " ".join(command.split()) == BANNED_FORCE_PUSH:
        return False  # the S2 example of what is banned, shown so it is never copied
    return sum(1 for a in tokens[1:] if not a.startswith("-")) < 2


def _toolkit_markdown() -> list[Path]:
    return sorted(TOOLKIT.rglob("*.md"))


def _inline_git_spans(path: Path) -> list[str]:
    """Every inline `git ...` code span of a file, whitespace normalized (spans may wrap lines)."""
    prose: list[str] = []
    in_fence = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        if _FENCE_RE.match(raw):
            in_fence = not in_fence
        elif not in_fence:
            prose.append(raw)
    text = " ".join(" ".join(prose).split())
    return [
        span.strip()
        for span in _INLINE_SPAN_RE.findall(text)
        if span.strip().startswith("git ")
    ]


def _all_commands() -> list[tuple[Path, int, str]]:
    return [
        (path, lineno, cmd)
        for path in _toolkit_markdown()
        for lineno, cmd in _fenced_commands(path)
    ]


# ---------------------------------------------------------------------------
# Detector proof
# ---------------------------------------------------------------------------

MUST_CATCH = [
    "git branch backup/$(git rev-parse --abbrev-ref HEAD)-$(date +%Y%m%d%H%M%S)",
    "GIT_SEQUENCE_EDITOR=true git rebase --autosquash -i <base>",
    "EDITOR=true GIT_SEQUENCE_EDITOR=true git rebase --autosquash -i <base>",
    "GIT_SEQUENCE_EDITOR='sed -i \"s/^pick <sha>/edit <sha>/\"' git rebase -i <sha>^",
    "git fsck --unreachable | grep commit",
    "git clone --no-local repo/ repo-rewrite/ && cd repo-rewrite/",
    "cd repo-rewrite/",
    "git grep -nE '^(<<<<<<<|=======|>>>>>>>)' || echo \"no markers\"",
    "git tag -a v1.2.3 -m \"Release v1.2.3\" && git push origin v1.2.3",
    "git commit -s -m \"$(cat <<'EOF'",
    "git -c core.editor=true rebase -i <base>",
    "git -C <worktree> -c rerere.autoupdate=true rebase <base>",
    "git rebase --continue; echo rc=$?",
    "git merge <branch> || true",
    "git log `git merge-base a b`..HEAD",
    "git rebase --continue | --skip | --abort",
    "git add <first set>;  git commit -m \"<first focused subject>\"",
]

MUST_NOT_CATCH = [
    EDITOR_EXCEPTION,
    "git grep -nE '^(<<<<<<<|=======|>>>>>>>)'",
    "git -C <fresh clone> filter-repo --path-glob '*.secret' --invert-paths",
    "git -C <worktree> rebase --rerere-autoupdate <base>",
    "git commit -m \"fix: keep a; in the subject\"",
    "git cherry-pick --rerere-autoupdate <sha>^..<sha2>",
    "gh pr create --repo <upstream-owner>/<repo> --base <branch> --head <your-user>:<your-branch>",
    "git checkout -b recovered HEAD@{N}",
    "date -u +%Y%m%d%H%M%S",
]


@pytest.mark.parametrize("command", MUST_CATCH)
def test_a_compound_or_prefixed_command_is_not_a_plain_call(command):
    assert shape_violations(command), f"detector missed a non-plain call: {command!r}"


@pytest.mark.parametrize("command", MUST_NOT_CATCH)
def test_a_plain_call_passes_the_shape_check(command):
    assert shape_violations(command) == [], f"detector flagged a plain call: {command!r}"


def test_comment_stripping_keeps_quoted_hashes():
    assert _strip_comment('git commit --fixup=<sha>   # "fixup! x"') == "git commit --fixup=<sha>"
    assert _strip_comment("git log --format='%H #x'") == "git log --format='%H #x'"


def test_continuation_lines_are_one_command(tmp_path):
    md = tmp_path / "x.md"
    md.write_text("```bash\ngh pr create --repo a/b \\\n  --title t | cat\n```\n", encoding="utf-8")
    [(_, cmd)] = _fenced_commands(md)
    assert shape_violations(cmd) == ["pipe"]


# ---------------------------------------------------------------------------
# The rules on the shipped prose
# ---------------------------------------------------------------------------

def test_the_toolkit_shows_shell_recipes_at_all():
    assert len(_all_commands()) > 50


def test_every_fenced_shell_command_in_the_toolkit_is_one_plain_call():
    offenders = [
        f"{path.relative_to(REPO_ROOT)}:{lineno}: {cmd}  -> {', '.join(problems)}"
        for path, lineno, cmd in _all_commands()
        if (problems := shape_violations(cmd))
    ]
    assert not offenders, "S12 command shape violated:\n" + "\n".join(offenders)


def test_the_only_editor_override_is_the_s12_exception_in_the_safety_contract():
    overrides = [
        (path, lineno, cmd)
        for path, lineno, cmd in _all_commands()
        if _EDITOR_VAR_RE.search(cmd)
    ]
    assert overrides, "the S12 exception must be shown once"
    for path, lineno, cmd in overrides:
        assert cmd == EDITOR_EXCEPTION, f"{path.relative_to(REPO_ROOT)}:{lineno}: {cmd}"
        assert path == SAFETY_CONTRACT, f"editor override outside S12: {path}:{lineno}"
    assert len(overrides) == 1


def test_no_recipe_stashes():
    offenders = [
        f"{path.relative_to(REPO_ROOT)}:{lineno}: {cmd}"
        for path, lineno, cmd in _all_commands()
        if _STASH_RE.search(cmd)
    ]
    assert not offenders, "S4 never stashes:\n" + "\n".join(offenders)


def test_no_recipe_hard_codes_a_sign_off():
    offenders = [
        f"{path.relative_to(REPO_ROOT)}:{lineno}: {cmd}"
        for path, lineno, cmd in _all_commands()
        if _COMMIT_SIGNOFF_RE.search(cmd)
    ]
    assert not offenders, "sign-off is added only when C4 requires it:\n" + "\n".join(offenders)


# ---------------------------------------------------------------------------
# S13: a new branch has no upstream until its first push
# ---------------------------------------------------------------------------

NEW_BRANCH_MUST_CATCH = [
    "git worktree add -b feat/x ../wt origin/19.0",
    "git worktree add ../wt -b feat/x origin/19.0",
    "git -C <repo> worktree add -B feat/x <worktree> origin/19.0",
    "git branch feat/x origin/19.0",
    "git branch backup/x-20260101 abc123",
    "git checkout -b feat/x origin/19.0",
    "git -C <worktree> switch -c feat/x origin/19.0",
]

NEW_BRANCH_MUST_NOT_CATCH = [
    "git worktree add --no-track -b feat/x <worktree> origin/19.0",
    "git branch --no-track feat/x origin/19.0",
    "git checkout --no-track -b feat/x origin/19.0",
    "git switch --no-track -c feat/x origin/19.0",
    "git worktree add <worktree> existing-branch",
    "git worktree list",
    "git worktree remove <worktree>",
    "git branch -D feat/x",
    "git branch --list",
    "git branch --show-current",
    "git switch --detach <sha>",
    "git switch feat/x",
    "git checkout feat/x",
]

PUSH_MUST_CATCH = [
    "git push",
    "git push --force-with-lease",
    "git push --set-upstream origin",
    "git -C <worktree> push",
]

PUSH_MUST_NOT_CATCH = [
    "git push --set-upstream <remote> <branch>",
    "git push --force-with-lease <remote> <branch>",
    "git push origin v1.2.3",
    "git push --force-with-lease origin <integration-branch>",
    BANNED_FORCE_PUSH,
    "git pull --rebase origin <branch>",
]


@pytest.mark.parametrize("command", NEW_BRANCH_MUST_CATCH)
def test_a_branch_creation_without_no_track_is_caught(command):
    assert creates_branch_without_no_track(command), f"detector missed: {command!r}"


@pytest.mark.parametrize("command", NEW_BRANCH_MUST_NOT_CATCH)
def test_a_tracking_free_or_non_creating_call_passes_the_branch_check(command):
    assert not creates_branch_without_no_track(command), f"detector flagged: {command!r}"


@pytest.mark.parametrize("command", PUSH_MUST_CATCH)
def test_a_push_that_leans_on_the_upstream_is_caught(command):
    assert push_without_remote_and_branch(command), f"detector missed: {command!r}"


@pytest.mark.parametrize("command", PUSH_MUST_NOT_CATCH)
def test_a_push_naming_remote_and_branch_passes(command):
    assert not push_without_remote_and_branch(command), f"detector flagged: {command!r}"


def test_every_recipe_that_creates_a_branch_says_no_track():
    """A branch cut from origin/<series> must not silently track (and so push to) that series."""
    offenders = []
    for path, lineno, cmd in _all_commands():
        if creates_branch_without_no_track(cmd):
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {cmd}")
    for path in _toolkit_markdown():
        offenders.extend(
            f"{path.relative_to(REPO_ROOT)}: inline `{span}`"
            for span in _inline_git_spans(path)
            if creates_branch_without_no_track(span)
        )
    assert not offenders, "S13: a new branch must be created with --no-track:\n" + "\n".join(offenders)


def test_the_branch_creation_forms_are_shown_at_all():
    """Guard against the scan going vacuous: the S9 addendum shows the four forms."""
    spans = _inline_git_spans(SAFETY_CONTRACT)
    created = [s for s in spans if _subcommand_tokens(s)[:1] and _subcommand_tokens(s)[0] in
               ("worktree", "branch", "checkout", "switch") and "--no-track" in s]
    assert len(created) >= 4


def test_every_recipe_push_names_its_remote_and_branch():
    offenders = [
        f"{path.relative_to(REPO_ROOT)}:{lineno}: {cmd}"
        for path, lineno, cmd in _all_commands()
        if push_without_remote_and_branch(cmd)
    ]
    assert not offenders, "S13: a push never relies on an upstream:\n" + "\n".join(offenders)


# ---------------------------------------------------------------------------
# One human gate; reported commit-message rewrites
# ---------------------------------------------------------------------------


