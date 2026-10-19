"""Guard: every command git-toolkit shows an agent is one plain call (S12 - Command shape).

Business rule: a git-toolkit agent copies the commands its prose shows. A subagent's Bash working
directory resets between calls and a permission layer judges each call by its literal text, so a
compound line (`a && b`, `x | grep`, `$(...)`, a leading `VAR=value`, `-c key=value`, `cd`) is
refused or misjudged at run time even though it reads fine on the page. S12 in
`plugins/git-toolkit/snippets/git-safety-contract.md` states the shape; this test keeps every
fenced shell block under `plugins/git-toolkit/` in that shape, keeps the one editor override where
S12 allows it, keeps `git stash` and a hard-coded `commit -s` out of the recipes (S4 never
stashes; C4 signs off only when required), and keeps every git-toolkit agent pointing at S12.

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
AGENTS_DIR = TOOLKIT / "agents"

SHELL_LANGS = {"bash", "sh", "shell", "console", "zsh"}

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


def _toolkit_markdown() -> list[Path]:
    return sorted(TOOLKIT.rglob("*.md"))


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


def test_s12_names_the_one_command_shape_and_its_exception():
    text = SAFETY_CONTRACT.read_text(encoding="utf-8")
    section = text.split("## S12 - Command shape", 1)
    assert len(section) == 2, "S12 - Command shape section missing"
    body = section[1].split("\n## ", 1)[0]
    assert "git -C <absolute worktree> <subcommand> <args>" in body
    assert EDITOR_EXCEPTION in body
    assert "var GIT_EDITOR" in body and "var GIT_SEQUENCE_EDITOR" in body


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


@pytest.mark.parametrize("agent", sorted(AGENTS_DIR.glob("*.md")), ids=lambda p: p.stem)
def test_every_toolkit_agent_cites_the_command_shape(agent):
    assert "S12" in agent.read_text(encoding="utf-8"), f"{agent.name} does not cite S12"


# ---------------------------------------------------------------------------
# One human gate; reported commit-message rewrites
# ---------------------------------------------------------------------------

CONSUMER_DELEGATION = REPO_ROOT / "plugins" / "odoo-ai-agents" / "snippets" / "git-delegation.md"
COMMIT_CONVENTION = TOOLKIT / "snippets" / "commit-convention.md"
RESULT_FIELDS = ("commit_subject:", "message_rewritten:")


def _gate_section() -> str:
    text = SAFETY_CONTRACT.read_text(encoding="utf-8")
    headings = [h for h in re.findall(r"^## .*$", text, re.M) if "human-confirm gate" in h.lower()]
    assert len(headings) == 1, f"expected one human-confirm gate section, found {headings}"
    return text.split(headings[0], 1)[1].split("### ", 1)[0]


def test_the_human_confirm_gate_lists_exactly_one_op_class():
    items = re.findall(r"^\d+\.\s+(.*(?:\n[ \t]+\S.*)*)", _gate_section(), re.M)
    assert len(items) == 1, f"the gate must list one op class, found {len(items)}: {items}"
    item = " ".join(items[0].split())
    assert "protected branch" in item and "pull request" in item


def test_rewrites_outside_protected_branches_are_self_decided():
    body = _gate_section()
    for op in ("force-with-lease to a feature or fork branch", "`branch -D`", "`reset --hard`",
               "filter-repo"):
        assert op in body, f"{op} must be named as self-decided"
    assert "never STOP to wait for a" in body


def test_no_citer_still_names_the_old_multi_item_gate():
    paths = _toolkit_markdown() + [CONSUMER_DELEGATION]
    offenders = [
        str(p.relative_to(REPO_ROOT)) for p in paths if "8-item" in p.read_text(encoding="utf-8")
    ]
    assert not offenders, "stale multi-item gate citation in: " + ", ".join(offenders)


@pytest.mark.parametrize("agent", ["git-operator", "github-operator", "git-pipeline-lead"])
def test_a_committing_agent_reports_the_final_subject_and_any_rewrite(agent):
    text = (AGENTS_DIR / f"{agent}.md").read_text(encoding="utf-8")
    block = text.split("## Output format", 1)[1].split("```", 2)[1]
    for field in RESULT_FIELDS:
        assert field in block, f"{agent} result block lacks {field}"


def test_inbound_validation_reports_a_rewrite_in_both_fields():
    text = COMMIT_CONVENTION.read_text(encoding="utf-8")
    c6 = text.split("## C6", 1)[1]
    for field in RESULT_FIELDS:
        assert f"`{field[:-1]}" in c6 or f"`{field}" in c6, f"C6 does not name {field}"
    assert "never rewrite silently" in c6


def test_sign_off_is_conditional_on_a_repo_requirement():
    c4 = COMMIT_CONVENTION.read_text(encoding="utf-8").split("## C4", 1)[1].split("## C5", 1)[0]
    assert "only when" in c4 and "REQUIRES" in c4
    assert "habit, not a requirement" in c4
