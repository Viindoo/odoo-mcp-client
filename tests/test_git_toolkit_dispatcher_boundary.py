"""Guard: the git-ops dispatcher states a REQUEST and a RESULT, never git or gh commands.

Business rule: how to operate git (which commands, which flags) is the git agents' job. That
know-how lives in the agents' own files (`agents/*.md`) and in the recipes they cite. Everything a
dispatcher reads - the `git-ops` skill and the snippets it points at for routing - describes what
to route and what outcome to expect. A command in that text leaks into briefs, overrides the
agent's own know-how, confuses it, and forks the source of truth.

Two behaviours are protected:

1. The dispatcher-facing text carries no git / GitHub-CLI command, no flag and no fenced shell
   block (whitespace normalized, prose included - a rule written in a sentence leaks as well as
   one written in a code span).
2. Every command recipe is reachable only through an agent: each file under
   `skills/git-ops/references/` and the scale recipes are cited by at least one agent, and none is
   cited by the skill.

The detector is a pure function of text, proved against a MUST-CATCH list (the shapes the skill
used to carry) and a MUST-NOT-CATCH list (prose that merely looks similar).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLKIT = REPO_ROOT / "plugins" / "git-toolkit"
SKILL = TOOLKIT / "skills" / "git-ops" / "SKILL.md"
REFERENCES = TOOLKIT / "skills" / "git-ops" / "references"
SNIPPETS = TOOLKIT / "snippets"
AGENTS = sorted((TOOLKIT / "agents").glob("*.md"))

# Snippets a dispatcher reads to route: they state outcomes, not commands.
DISPATCHER_SNIPPETS = [
    SNIPPETS / "git-delegation-decision.md",
    SNIPPETS / "git-scale-protocol.md",
    SNIPPETS / "git-model-tiers.md",
]
# The command recipes agents read; no dispatcher-facing file may point at them.
AGENT_ONLY_RECIPES = sorted(REFERENCES.glob("*.md")) + [SNIPPETS / "git-scale-recipes.md"]

_GIT_SUBCOMMANDS = (
    "status|log|show|diff|rebase|merge|cherry-pick|push|pull|fetch|commit|reset|branch|checkout|"
    "switch|worktree|stash|bisect|filter-repo|clone|tag|add|rm|restore|revert|range-diff|"
    "rev-parse|blame|config|ls-remote|remote|reflog|clean|apply|am|describe|grep|init|mv|"
    "sparse-checkout|lfs|submodule|var|merge-base|cat-file|fsck|format-patch|gc|prune|notes"
)
_GH_SUBCOMMANDS = "pr|issue|release|run|api|repo|auth|workflow|search|label|gist|browse|status|checks"
_GIT_CMD_RE = re.compile(rf"(?<![\w-])git\s+(?:-C\s+\S+\s+)?(?:{_GIT_SUBCOMMANDS})\b")
_GH_CMD_RE = re.compile(rf"(?<![\w-])gh\s+(?:{_GH_SUBCOMMANDS})\b")
# A flag: one or two hyphens glued to a word, not itself inside a word or a hyphenated name.
_FLAG_RE = re.compile(r"(?<![\w-])-{1,2}[A-Za-z][\w-]*")
_FENCE_RE = re.compile(r"^\s*```+\s*(\w*)\s*$")
_SHELL_FENCE_LANGS = {"", "bash", "sh", "shell", "console", "zsh"}


def _normalized(text: str) -> str:
    return " ".join(text.split())


def command_leaks(text: str) -> list[str]:
    """Why `text` carries git / gh command know-how ([] when it states outcomes only)."""
    problems = []
    in_fence = False
    for line in text.splitlines():
        match = _FENCE_RE.match(line)
        if not match:
            continue
        if not in_fence and match.group(1).lower() in _SHELL_FENCE_LANGS:
            problems.append("fenced shell block")
            break
        in_fence = not in_fence
    flat = _normalized(text)
    problems += [f"git command: {m.group()}" for m in _GIT_CMD_RE.finditer(flat)]
    problems += [f"gh command: {m.group()}" for m in _GH_CMD_RE.finditer(flat)]
    problems += [f"flag: {m.group()}" for m in _FLAG_RE.finditer(flat)]
    return problems


MUST_CATCH = [
    "run git status and report",
    "Run `git merge --no-ff` to keep history",
    "read `--name-only`/`--numstat` summaries first",
    "sign off (`-s`) only when the repo requires it",
    "git\n  rebase the branch",
    "git -C <worktree> log -n 5",
    "gh pr list",
    "gh\npr view 12",
    "```bash\ngit status\n```",
    "```\ngit status\n```",
    "pass --force-with-lease",
]

MUST_NOT_CATCH = [
    "Front door for any git or GitHub task, however casually asked",
    "the git-ops skill routes to git-surveyor and git-operator",
    "git-toolkit:git-ops",
    "A - B and a hyphenated word like read-only or cherry-pick as a bare op name",
    "Reading the result of a finished bisect is a READ",
    "push, branch, rebase, merge in a list of op names",
    "the GitHub CLI as fallback",
    "`${CLAUDE_PLUGIN_ROOT}/snippets/git-nesting-protocol.md` N0",
    "```yaml\nkey: value\n```",
]


@pytest.mark.parametrize("text", MUST_CATCH)
def test_command_text_is_detected(text):
    assert command_leaks(text), f"detector missed command text: {text!r}"


@pytest.mark.parametrize("text", MUST_NOT_CATCH)
def test_outcome_prose_is_not_flagged(text):
    assert command_leaks(text) == [], f"detector flagged prose: {text!r}"


def test_the_git_ops_skill_states_outcomes_and_no_commands():
    leaks = command_leaks(SKILL.read_text(encoding="utf-8"))
    assert not leaks, "git-ops must describe request + result, never commands:\n" + "\n".join(leaks)


@pytest.mark.parametrize("path", DISPATCHER_SNIPPETS, ids=lambda p: p.name)
def test_dispatcher_facing_snippets_state_outcomes_and_no_commands(path):
    leaks = command_leaks(path.read_text(encoding="utf-8"))
    assert not leaks, f"{path.name} is read by the dispatcher:\n" + "\n".join(leaks)


def test_the_skill_routes_every_kind_of_op_to_an_agent():
    """No op class is left for the dispatcher to run itself."""
    text = SKILL.read_text(encoding="utf-8")
    for agent in ("git-surveyor", "git-operator", "github-operator", "git-pipeline-lead"):
        assert agent in text, f"git-ops never routes to {agent}"


def _agents_citing(recipe: Path) -> list[Path]:
    needle = f"{recipe.parent.name}/{recipe.name}"
    return [a for a in AGENTS if needle in a.read_text(encoding="utf-8")]


@pytest.mark.parametrize("recipe", AGENT_ONLY_RECIPES, ids=lambda p: p.name)
def test_a_command_recipe_is_cited_by_an_agent(recipe):
    assert _agents_citing(recipe), f"{recipe.name} is cited by no agent file; it is an orphan recipe"


@pytest.mark.parametrize("recipe", AGENT_ONLY_RECIPES, ids=lambda p: p.name)
def test_no_dispatcher_facing_file_points_at_a_command_recipe(recipe):
    for reader in [SKILL] + DISPATCHER_SNIPPETS:
        assert recipe.name not in reader.read_text(encoding="utf-8"), (
            f"{reader.name} is read by the dispatcher but cites the agent recipe {recipe.name}"
        )
