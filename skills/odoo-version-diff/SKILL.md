# odoo-version-diff

**Persona:** Developer + Marketer
**Triggers:** what changed between Odoo 16 and 17, new API in version 17, breaking changes in upgrade, API nào thay đổi từ v16 sang v17, tính năng mới Odoo 17
**Tools used:** `api_version_diff`, `lookup_core_api`

## Instructions

This skill produces a comprehensive diff of API and feature changes between two Odoo versions. It serves both developers (who need breaking changes and migration paths) and marketers (who need feature highlights and business-value descriptions).

Call `api_version_diff` with the source and target versions to retrieve the full set of API changes. For each removed or changed symbol, call `lookup_core_api` to get documentation on the replacement. Categorize results into four buckets: Added (new APIs available), Removed (will break existing code), Deprecated (still works but should be migrated), and Changed signatures (same name but different parameters or return type).

Present the diff in a structured, scannable format. For a Developer audience, include file paths and migration notes. For a Marketer audience, translate technical changes into business-value language in a separate "Feature highlights" section. Always note which changes affect module developers vs. end-user functionality.

## Output format

## Version Diff: Odoo <from> → <to>

### Added APIs (<N> new)
| Symbol | Module | Description |
|--------|--------|-------------|
| ...    | ...    | ...         |

### Removed APIs (<N> breaking)
| Symbol | Last version | Replacement |
|--------|-------------|-------------|
| ...    | ...         | ...         |

### Deprecated APIs (<N> warnings)
| Symbol | Deprecation message | Replacement |
|--------|--------------------|----|
| ...    | ...                | ...|

### Changed signatures (<N>)
| Symbol | Old signature | New signature | Notes |
|--------|--------------|---------------|-------|
| ...    | ...          | ...           | ...   |

### Feature highlights (business value)
- <highlight 1>
- <highlight 2>

## Example invocation

User: "what changed between Odoo 16 and 17 for module developers?"
Expected output: Categorized diff with Added/Removed/Deprecated/Changed sections, plus a plain-language feature highlights section suitable for non-technical stakeholders.
