<!-- SSOT snippet. The single home for commit-message formatting: the mandatory universal
     business-subject rule, length limits, the convention-detection protocol, the DCO sign-off
     post-condition, and the inbound-validation gate on any caller-supplied message. Points at the
     two reference standards. Referenced via ${CLAUDE_PLUGIN_ROOT}/snippets/commit-convention.md
     by every committing agent (git-operator, git-pipeline-lead, github-operator). Edit here only. -->

# Commit Convention (SSOT)

Every commit this toolkit creates MUST follow a DETECTED convention, and MUST satisfy the universal
rule below regardless of which convention applies. Consult this snippet BEFORE any `git commit`, PR
title, or PR body. A caller-supplied message is never exempt - see C6.

## C1 - Mandatory universal rule (applies to EVERY convention + any project override)

The subject states the BUSINESS problem or outcome the commit solves (WHAT / WHY), NOT the
implementation (HOW).

- Self-test: "Can a reader grasp the business impact WITHOUT reading the diff?" If not, rewrite the
  subject.
- BAD (HOW): `fix: remove null check in user service`.
  GOOD (WHAT/WHY): `fix: prevent crash when user has no email address`.
- Imperative mood ("Add"/"Fix"/"Prevent", not "Added"/"Fixes"): the subject completes "If applied,
  this commit will ___".
- Capitalize the first word of the description; no trailing period.
- Blank line REQUIRED between subject and body. Body explains WHY, not HOW (the diff shows HOW).

## C2 - Length limits

- Subject: soft target 50 chars, HARD ceiling 72 (GitHub truncates ~69 + "..."; PR auto-title cuts
  at 72). Never exceed 72.
- Body: wrap every line at 72 chars.

## C3 - Detection protocol (in order - first match wins)

1. **Explicit project guideline WINS.** Scan `CONTRIBUTING*.md`, `COMMIT_CONVENTION.md`,
   `.gitmessage`, and docs for a stated commit rule. If found, that is the SSOT - it OVERRIDES the
   built-in standards on any conflict.
2. **Else infer from history:** `git log --no-merges -n 30 --format=%s`, then:
   - `^\[(FIX|IMP|ADD|REM|REF|MOV|REV|MERGE|CLA|I18N|REL|PERF|CLN|LINT)\]` with >= 3 hits ->
     the ODOO standard.
   - `^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\(.+\))?!?:` with >= 3 hits
     -> the GENERAL (Conventional Commits) standard.
3. **Else repo-type:** a `__manifest__.py` present (Odoo modules) -> ODOO; otherwise -> GENERAL
   (the default).

On detect, load the matching reference and format accordingly:

- GENERAL -> `${CLAUDE_PLUGIN_ROOT}/skills/git-ops/references/commit-convention-general.md`
- ODOO -> `${CLAUDE_PLUGIN_ROOT}/skills/git-ops/references/commit-convention-odoo.md`

## C4 - Sign-off (DCO)

When the repo requires sign-off (a `DCO` check, a `Signed-off-by` trailer in recent history, or a
CONTRIBUTING note), append it with `git commit -s` - it adds `Signed-off-by:` from
`git config user.name`/`user.email`. For an existing range, `git rebase --signoff <base>`.

Sign-off is a POST-condition, not an intention. After committing, confirm the `Signed-off-by:`
trailer is present on the new commit (`git log -1 --format='%(trailers:key=Signed-off-by)'`). A
commit created without it is not DONE - amend it before you report.

## C5 - Multi-line commit from a shell

```bash
git commit -s -m "$(cat <<'EOF'
<type/tag>: business-outcome subject (<= 72 chars)

Body paragraph: WHY this change, the business problem it solves.
Wrap at 72 chars.

Closes #N
EOF
)"
```

## C6 - Inbound validation (a supplied message is INPUT, never output)

A caller may hand you a `commit-msg`. It is a proposal, not an instruction. Before any `git commit`:

1. Detect the repo's convention (C3).
2. Match the supplied subject against that standard's grammar.
3. Match -> use it. Mismatch -> REWRITE the subject into the detected standard from the caller's
   stated files + business outcome, and say in your report that you rewrote it and why.
4. Neither a conforming message NOR a business outcome to rewrite from -> STOP:
   `NEEDS_CONTEXT(business-outcome)`.

Never commit a string you did not validate. A caller-stated format preference is a hint; it never
overrides the convention you detected.
