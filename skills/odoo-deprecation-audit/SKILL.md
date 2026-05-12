# odoo-deprecation-audit

**Persona:** Developer
**Triggers:** audit deprecated API usage, upgrade readiness check, find old-style code before upgrade, kiểm tra deprecated API, chuẩn bị upgrade Odoo
**Tools used:** `find_deprecated_usage`, `api_version_diff`, `lookup_core_api`

## Instructions

This skill performs a systematic audit of deprecated Odoo API usage in preparation for a version upgrade. It is intended for developers who need a complete, actionable list of code changes required before migrating to a new Odoo version.

Begin by calling `find_deprecated_usage` to scan the codebase for all deprecated symbols in the current version. Then call `api_version_diff` between the current and target versions to identify symbols that were deprecated in intermediate releases and are now fully removed. Use `lookup_core_api` to retrieve the official replacement API for each deprecated symbol found.

Produce a prioritized table of deprecated usages. Assign urgency based on whether the symbol is deprecated (warning in current version) or removed (breaks immediately in target version). Group by file so developers can batch-fix one file at a time. Always include the exact replacement API with a brief migration note.

## Output format

## Deprecation Audit Report

**Source version:** <from>
**Target version:** <to>
**Files scanned:** <N>
**Issues found:** <N>

| File | Line | Deprecated symbol | Replacement | Urgency |
|------|------|-------------------|-------------|---------|
| ...  | ...  | ...               | ...         | WARN/BREAKING |

### Migration notes
- <key migration pattern 1>
- <key migration pattern 2>

### Estimated migration effort
<Low/Medium/High> — <rationale>

## Example invocation

User: "audit deprecated API usage before we upgrade from Odoo 16 to 17"
Expected output: A table of all deprecated/removed API usages by file and line, with replacement APIs and urgency ratings, plus estimated migration effort.
