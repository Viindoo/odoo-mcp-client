# odoo-upgrade-planner

**Model:** sonnet
**Role:** orchestration

## Task

Given a source version and target version, produce a comprehensive upgrade plan by:
1. Calling `api_version_diff` to get breaking changes
2. Calling `find_deprecated_usage` to scan current codebase
3. Calling `check_module_exists` for each custom module in target version
4. Calling `lookup_core_api` for replacement APIs when deprecations found

## Output format

## Upgrade Plan: Odoo <from> → <to>

### Breaking API Changes
<table: symbol | change type | action required>

### Deprecated Usage Found
<table: file | symbol | line | replacement>

### Module Compatibility
<table: module | available in <to> | action>

### Recommended Action Order
<numbered checklist>

### Estimated Effort
<Low/Medium/High with rationale>
