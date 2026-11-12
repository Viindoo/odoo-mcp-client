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
- A message and a pull request body describe the NET change against the base branch - what the
  code does once merged. Steps the branch took and later undid, review rounds and earlier attempts
  are not part of it.

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

## C4 - Sign-off only when the repo requires it

Sign off (`git commit -s`, which adds `Signed-off-by:` from `user.name`/`user.email`) only when
the repo REQUIRES it, which is one of:

1. a configured DCO check - `.github/dco.yml`, or a workflow under `.github/workflows/` that runs a
   DCO / sign-off check;
2. a stated requirement in `CONTRIBUTING*`, `README*`, the pull request template or `.gitmessage`;
3. a brief that says sign-off is required.

Detect it read-only, one command per call, and read every hit - a passing mention of DCO is not a
requirement:

```bash
git ls-files -- .github/dco.yml
git grep -n -E -e 'DCO' -e 'Developer Certificate of Origin' -e 'Signed-off-by' -e '--signoff' -- .github 'CONTRIBUTING*' 'README*' '.gitmessage'
```

`Signed-off-by` trailers in the history alone are a contributor's habit, not a requirement.

When required, sign-off is a POST-condition, not an intention: after committing, confirm the
`Signed-off-by:` trailer is present on the new commit
(`git log -1 --format='%(trailers:key=Signed-off-by)'`); a commit created without it is not DONE -
amend it before you report. When required for an existing range: `git rebase --signoff <base>`.

## C5 - Multi-line commit message

Write the message with the `Write` tool into a file beside the findings file:

```
<type/tag>: business-outcome subject (<= 72 chars)

Body paragraph: WHY this change, the business problem it solves.
Wrap at 72 chars.

Closes #N
```

Then commit from it in one plain call (S12 in
`${CLAUDE_PLUGIN_ROOT}/snippets/git-safety-contract.md`), adding `-s` when C4 requires sign-off:

```bash
git commit -F <message-file>
```

A one-line message may go in with `-m "<subject>"` instead.

## C6 - Inbound validation (a supplied message is INPUT, never output)

A caller may hand you a `commit-msg`. It is a proposal, not an instruction. Before any `git commit`:

1. Detect the repo's convention (C3).
2. Match the supplied subject against that standard's grammar. A tag or type the detected
   standard's table does not list, including a near spelling, is a mismatch: rewrite it to the
   table's tag and report it.
3. Match -> use it. Mismatch -> REWRITE the subject into the detected standard from the caller's
   stated files + business outcome, and report it in `message_rewritten:` beside
   `commit_subject:`; never rewrite silently.
4. Neither a conforming message NOR a business outcome to rewrite from -> STOP:
   `NEEDS_CONTEXT(business-outcome)`.

Never commit a string you did not validate. A caller-stated format preference is a hint; it never
overrides the convention you detected.

## C7 - Branch history: complete changes, no derivative commit

The commits a branch adds over its base are the history its pull request shows. Each one states
one business outcome and holds everything that outcome needs, so the list reads as the changes
made and any one of them can be reverted alone. A commit that exists only to correct another
commit of the same branch (a derivative commit) never stays in that history.

- **A correction is folded into the commit it corrects.** Commit A fixes X and causes Y: the fix
  of Y is part of A. Commit E adds a feature and a defect shows up in it later: that fix is part
  of E. The same holds for a review or CI correction, a test or doc that change lacked, a typo.
- **A change carries the adjustments it forces.** Adding or removing a component (a module, a
  package, an API) and the edits that forces in the code depending on it are ONE commit.
- **A change with an outcome of its own is its own commit** - a defect that predates the branch
  included.

A commit request that states `corrects: <the commit, or what it introduced>` is folded: find
that commit among the ones the branch adds, commit the change as its fixup and autosquash
(`${CLAUDE_PLUGIN_ROOT}/skills/git-ops/references/history-rewrite.md`) under S1 and S6 - the tree
after the rewrite equals the tree with the change committed on top - then push again with
force-with-lease (S2) when the branch was pushed before. Report `folded_into:` with the subject
of that commit. A request without `corrects:` is committed as asked. Never fold into a commit
the base already holds or on a protected branch; where the project's guideline forbids rewriting
a pushed branch (C3 rule 1), commit on top and say so in the report.
