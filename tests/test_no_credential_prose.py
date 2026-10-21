"""Guard: agent-facing prose carries no credential instruction.

Owner rule: a runtime AI agent is never told anything about a password, an API key, a login, a
token, a secret or a session cookie - where to read, ask for, store, pass or export one, which user
logs in, or to ask a human for one. The agent knows how to reach an instance it built, and a human
never supplies a password. Prose that mentions the vocabulary at all is how the instruction creeps
back, so this test scans EVERY file an agent can read, in all three plugins, for the vocabulary.

What it scans: every file under `plugins/<plugin>/<dir>/` with a text suffix, EXCEPT the code
directories (`scripts`, `generator`, `.claude-plugin`, which are code or manifests, not prose) and
the files that sit at a plugin's root (READMEs, the maintainer reports). Whitespace is normalised
(a phrase wrapped over two lines still matches) and matching is case-insensitive.

What it allows: an explicit list, one entry per file, each with the reason. An entry is either a
whole file (a human install document, an IDE snippet, the connect command, the code-review rules
about hardcoded secrets) or a SHAPE inside one file (a regex over the text around the match: the
Odoo test API `login=` argument, a customer usage metric). An entry never forgives a virtue such as
"this file is about security"; a line in an allowlisted shape that is not in the shape fails. An
entry nothing matches any more fails too, so the list cannot outlive the prose it excused.

Run with: python3 -m pytest tests/test_no_credential_prose.py -q
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS = REPO_ROOT / "plugins"

TEXT_SUFFIXES = (".md", ".yaml", ".yml", ".txt", ".sh", ".json")
CODE_DIRS = frozenset({"scripts", "generator", ".claude-plugin"})

# The credential vocabulary. Qualified for "token": a lease token or a design token is not a
# credential, an access / auth / API / bearer / session / CSRF / personal-access token is.
# A word is not a match inside a longer word ("design instead", "secretary") but is one when it is
# joined by an underscore (ODOO_PG_PASSWORD, GITHUB_PERSONAL_ACCESS_TOKEN): the guards are letters.
VOCABULARY = re.compile(
    r"""
    (?<![A-Za-z])(?:
      pass(?:word|wd|phrase)s?
    | api[ _-]?keys?
    | ssh[ _-]keys? | private[ _-]keys?
    | secrets?
    | credentials?
    | (?:re-?)?log(?:ged|s|ging)?[ -]?in | logins?
    | sign(?:ed|s|ing)?[ -]?in
    | cookies?
    | pgpass | storageState
    | /web/login
    | admin/admin
    | (?:access|auth|api|bearer|session|csrf|refresh|oauth|personal[ _-]access|github|bot)[ _-]?tokens?
    | X-API-Key
    )(?![A-Za-z])
    """,
    re.IGNORECASE | re.VERBOSE,
)

WINDOW = 70  # characters of normalised text on each side of a match an allowlist shape may read


@dataclass(frozen=True)
class Allow:
    path: str            # fnmatch pattern over the repo-relative path
    reason: str
    shape: str = ""      # regex over the text around a match; empty = the whole file is allowed

    def covers(self, rel, context):
        if not fnmatch(rel, self.path):
            return False
        return not self.shape or re.search(self.shape, context, re.IGNORECASE) is not None


A = "plugins/odoo-ai-agents/"
IDE_SNIPPETS = (
    "antigravity-mcp.json", "continue-dev-mcp.yaml", "cursor-mcp.json", "cursor-rules.md",
    "gemini-gem-instructions.md", "jetbrains-mcp-config.md", "junie-mcp.json",
    "openai-gpt-instructions.md", "vscode-mcp.json", "windsurf-mcp.json", "zed-mcp.json",
)

ALLOWLIST = (
    # --- code-review rules: hardcoded secrets in the REVIEWED code ---------------------------
    Allow(A + "skills/odoo-security-audit/*", "the audit rules and examples about a hardcoded secret in reviewed code"),
    Allow(A + "skills/odoo-intake/SKILL.md", "routing phrase for the security audit",
          shape=r'"hardcoded secret"'),
    # --- the Odoo test API --------------------------------------------------------------------
    Allow(A + "skills/_shared/coding_guidelines/*/tests.md", "the start_tour(login=...) argument of Odoo's test API",
          shape=r'login="admin"'),
    Allow(A + "skills/_shared/coding_guidelines/*/python.md", "the Odoo symbol login_redirect in an import example",
          shape=r"import login_redirect"),
    Allow("plugins/git-toolkit/agents/github-operator.md", "a tool name in the agent's tool grant",
          shape=r"run_secret_scanning"),
    # --- non-credential senses of the words ---------------------------------------------------
    Allow(A + "skills/odoo-customer-health/*", "a customer's login frequency is a usage metric",
          shape=r"login frequency|log in daily|rarely log in|login / adoption"),
    Allow(A + "skills/odoo-deploy-checklist/references/checklist-template.md",
          "a go-live smoke flow of the deployed system",
          shape=r"critical flows verified: login"),
    Allow(A + "snippets/context-handoff-protocol.md", "the word is banned as a framing of a payload",
          shape=r'"secret"|secret framing'),
    Allow(A + "snippets/master-child-design-contract.md", "the word is banned as a framing of a design",
          shape=r'"secret"/"private"'),
    Allow(A + "snippets/visual-evidence-lifecycle-contract.md", "about guessability of a run-slug name",
          shape=r"never as a secret either"),
    Allow(A + "docs/reference/INSTANCE-LIFECYCLE-BUILD-CONTRACT.md", "a readiness-probe URL, no sign-in is performed",
          shape=r"fallback `/web/login`"),
    # --- human-only documents and IDE snippets ------------------------------------------------
    *(Allow(A + "snippets/" + name, "IDE MCP snippet: the X-API-Key placeholder, pinned by tests/test_snippets.py")
      for name in IDE_SNIPPETS),
    Allow(A + "docs/setup.md", "human install document"),
    Allow(A + "docs/personas/*", "human persona documents"),
    Allow("plugins/git-toolkit/docs/*", "human architecture document"),
    # --- left as is by the owner --------------------------------------------------------------
    Allow("plugins/odoo-semantic-mcp/commands/connect.md", "the connect command registers the server URL and key"),
)


def normalise(text):
    """`text` with every run of whitespace as one space, and for each character of the result the
    1-based line of the original it came from."""
    out, lines = [], []
    line = 1
    pending_space = False
    for ch in text:
        if ch.isspace():
            pending_space = True
            if ch == "\n":
                line += 1
            continue
        if pending_space and out:
            out.append(" ")
            lines.append(line)
        pending_space = False
        out.append(ch)
        lines.append(line)
    return "".join(out), lines


def hits(text):
    """[(line, matched word, surrounding normalised text)] for every vocabulary match."""
    flat, lines = normalise(text)
    found = []
    for m in VOCABULARY.finditer(flat):
        lo, hi = max(0, m.start() - WINDOW), min(len(flat), m.end() + WINDOW)
        found.append((lines[m.start()], m.group(0), flat[lo:hi]))
    return found


def prose_files():
    for plugin in sorted(p for p in PLUGINS.iterdir() if p.is_dir()):
        for path in sorted(plugin.rglob("*")):
            if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
                continue
            parts = path.relative_to(plugin).parts
            if len(parts) < 2 or parts[0] in CODE_DIRS or "node_modules" in parts:
                continue
            yield path.relative_to(REPO_ROOT).as_posix(), path


def scan():
    """(violations, the allowlist entries that excused at least one match)."""
    violations, used = [], set()
    for rel, path in prose_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line, word, context in hits(text):
            covering = [i for i, a in enumerate(ALLOWLIST) if a.covers(rel, context)]
            if covering:
                used.update(covering)
            else:
                violations.append("%s:%d: %r in: ...%s..." % (rel, line, word, context))
    return violations, used


def test_agent_facing_prose_carries_no_credential_instruction():
    violations, _ = scan()
    assert not violations, (
        "credential vocabulary in agent-facing prose (delete the line; do not reword it into another "
        "credential hint; a legitimate non-credential sense goes into ALLOWLIST with its reason):\n"
        + "\n".join(violations)
    )


def test_every_allowlist_entry_still_excuses_something():
    _, used = scan()
    stale = [a for i, a in enumerate(ALLOWLIST) if i not in used]
    assert not stale, "allowlist entries nothing matches any more (delete them):\n" + "\n".join(
        "%s  shape=%r  (%s)" % (a.path, a.shape, a.reason) for a in stale
    )


def test_scanner_sees_a_credential_phrase_however_it_is_written():
    # The guard protects the owner rule, so it must catch the wrapped, upper-cased and
    # underscore-spelled forms and must not trip on the unrelated senses of the same letters.
    must_flag = [
        "Ask for the password once.",
        "export ODOO_DOC_PASSWORD before the run",
        "fill the form at /web/login",
        "then log\n  in as admin",
        "reuse the saved storageState file",
        "send the X-API-Key header",
        "a GITHUB_PERSONAL_ACCESS_TOKEN env var",
        "NEEDS_CONTEXT(PASSWORD)",
        "admin/admin",
    ]
    must_pass = [
        "Never derive it from a lease_token.",
        "the lease token returned by lease_acquire",
        "a design token resolves EMPTY",
        "the other design instead of this one",
        "go to the log inline",
        "a Claude session",
    ]
    for text in must_flag:
        assert hits(text), "not flagged: %r" % text
    for text in must_pass:
        assert not hits(text), "flagged: %r -> %r" % (text, hits(text))
