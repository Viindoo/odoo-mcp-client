# Commit Convention - GENERAL standard

Loaded by `${CLAUDE_PLUGIN_ROOT}/snippets/commit-convention.md` when detection resolves to GENERAL
(Conventional Commits, or a non-Odoo repo by default). The universal business-subject rule and the
50/72 limits in that snippet ALWAYS apply on top of this.

## Subject format

Conventional Commits when the repo uses it:

```
<type>[(<scope>)][!]: <description>
```

Classic when no convention is detected:

```
<Capitalized imperative verb> <object> [in/for/when <context>]
```

## Types (Conventional Commits)

| Type | When | SemVer |
|---|---|---|
| `feat` | new user-facing feature | MINOR |
| `fix` | bug fix | PATCH |
| `docs` | docs only | PATCH |
| `style` | formatting, no logic change | PATCH |
| `refactor` | restructure, no behavior change | PATCH |
| `perf` | performance | PATCH |
| `test` | add/fix tests | PATCH |
| `build` | build system, deps | PATCH |
| `ci` | CI config | PATCH |
| `chore` | tooling, maintenance | PATCH |
| `revert` | revert a prior commit | PATCH |

Breaking change: append `!` after type/scope OR add a `BREAKING CHANGE:` footer (correlates MAJOR).

## Subject rules

Imperative mood, capitalized, no trailing period, business-subject (WHAT/WHY not HOW), subject soft
50 / HARD 72, body wraps at 72, blank line before body - all per C1/C2 of
`${CLAUDE_PLUGIN_ROOT}/snippets/commit-convention.md`.

## Body

Blank line, then WHY this change (business problem, motivation, trade-offs, rejected alternatives).
The diff shows HOW; do not restate it. Body is optional for a small atomic change; required when the
why is non-obvious or there is migration/breakage risk.

## Footers (after body, one blank line before the block; no blank lines between entries)

```
Fixes #123
Closes #456
BREAKING CHANGE: <what breaks + how to migrate>
Co-authored-by: Name <email@host>
Signed-off-by: Name <email@host>
```

- `Fixes`/`Closes`/`Resolves` + `#N` auto-closes the GitHub issue on merge (case-insensitive
  variants: fix, fixes, fixed, close, closes, closed, resolve, resolves, resolved).
- `BREAKING CHANGE:` must be uppercase.
- `Signed-off-by:` is appended by `git commit -s` (DCO).

## Example (GOOD)

```
feat(billing): prevent double-charge on network retry

PaymentService retried the charge RPC on any 5xx, but the gateway was
already processing the original request. Customers were occasionally
billed twice for the same order.

Closes #1892
Signed-off-by: Name <email@host>
```

## Shell HEREDOC

```bash
git commit -s -m "$(cat <<'EOF'
feat(scope): business-outcome subject

Body explaining WHY. Wrap at 72.

Closes #N
EOF
)"
```
