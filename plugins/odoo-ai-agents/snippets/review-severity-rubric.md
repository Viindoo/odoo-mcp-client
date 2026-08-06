<!-- SSOT snippet. Defines the ONE severity scale, the audit-tier mapping, the diff fold-in rule,
     and the ownership-transfer/dedup rule shared by the review-plus-audit pipeline. Referenced
     (not copy-pasted) by agents/odoo-code-reviewer.md (including its `### Step 3.6 - Audit
     escalation`) and by skills/odoo-perf-audit/SKILL.md, skills/odoo-security-audit/SKILL.md,
     and skills/odoo-deprecation-audit/SKILL.md.
     Edit here only; consumers point at ${CLAUDE_PLUGIN_ROOT}/snippets/review-severity-rubric.md. -->

# Review Severity Rubric

Do not invent a second severity scale or a parallel vocabulary anywhere in the review-plus-audit
pipeline. Every finding - reviewer or audit - reports on this one scale, folds in by this one rule,
and is owned by exactly one producer per pass.

## 1. The scale (single source)

**CRITICAL / HIGH / MED / LOW** - the scale already defined in `agents/odoo-code-reviewer.md`'s
`## Severity & scoring` table (D1-D7 dimensions) is the single source. The three dedicated audits do
not define their own scale; they map their native tiers into this one (`## 2`).

## 2. Audit-tier mapping (version-neutral)

Map by IMPACT, never by a hardcoded Odoo version or version range - the same tier name carries the
same severity on every indexed series.

- **`odoo-deprecation-audit`** (D5 owner on escalation): `BREAKING` -> CRITICAL or HIGH (CRITICAL
  when the symbol is already removed at the pinned version; HIGH when deprecated with removal
  scheduled but still present); `WARN` -> MED; `STYLE` -> LOW.
- **`odoo-security-audit`** (D2 owner on escalation): exploit-path severity maps directly to
  CRITICAL/HIGH/MED/LOW (e.g. an unauthenticated injection/RCE path is CRITICAL; a
  privilege-widening `sudo()` is HIGH; a missing `groups=` on a low-sensitivity field is MED; a
  hardening nit is LOW).
- **`odoo-perf-audit`** (D3 owner on escalation): impact maps directly to CRITICAL/HIGH/MED/LOW
  (e.g. an unbounded query hot-pathed on a high-volume model is CRITICAL/HIGH; an N+1 in a
  low-volume loop is MED; a missing `index=True` with no observed load is LOW).

## 3. Fold-in rule (diff vs pre-existing)

- An audit finding **inside the diff** at CRITICAL or HIGH forces the review verdict to
  `REQUEST_CHANGES`. MED/LOW findings inside the diff are advisory - recorded, but they do not by
  themselves flip the verdict.
- An audit finding **outside the diff** (pre-existing / blast-radius) never changes the diff
  verdict or score, at any severity. It surfaces as a `concerns:` sibling note carrying an
  opt-in `next:` (e.g. `next: odoo-deprecation-audit` for a full pre-existing sweep) - never
  silently dropped, never silently blocking the diff.

## 4. Ownership-transfer / dedup rule (F2)

When a dimension escalates to its dedicated audit for a given pass, the reviewer's inline check for
that dimension DEGRADES TO TRIGGER-ONLY: it may still flag "escalate" but emits NO authoritative
findings for that dimension. The audit becomes the SOLE owner of that dimension's findings in the
merged report.

Concretely:
- `odoo-security-audit` fires -> D2's inline findings are suppressed in the merged report; D2 keeps
  only its trigger role.
- `odoo-perf-audit` fires -> D3's inline findings are suppressed in the merged report; D3 keeps only
  its trigger role.
- `odoo-deprecation-audit` fires -> D5's inline findings are suppressed in the merged report; D5
  keeps only its trigger role.

Deterministic dedup key: **(dimension, file:line, symbol)**. Two entries sharing a key collapse to
the audit's entry - a collision never resolves to the reviewer's inline entry.

## 5. One scale, one owner, everywhere

This rubric is referenced by `agents/odoo-code-reviewer.md` and by the three audit skills
(`skills/odoo-perf-audit/SKILL.md`, `skills/odoo-security-audit/SKILL.md`,
`skills/odoo-deprecation-audit/SKILL.md`) so one scale and one owner governs the whole pipeline.
