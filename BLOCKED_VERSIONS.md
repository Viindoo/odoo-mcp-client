# BLOCKED_VERSIONS

This file is the **kill-switch registry** for the Odoo MCP Client plugin.

When a commit SHA is listed here, the `pin-sha.yml` workflow will **skip** pinning
that commit to the Claude marketplace (`Viindoo/claude-plugins`). This prevents a
known-bad build from propagating to end-users who run `claude plugin update`.

**End-user action:** if you installed a version listed below, run
`claude plugin update odoo-semantic-skills@viindoo-plugins` (which pulls the
`odoo-semantic-mcp` plugin via its dependency) once the block is lifted, or
roll back manually by following the [rollback runbook](CONTRIBUTING.md#rollback-runbook).

## Blocked SHAs

| Version | SHA | Reason | Workaround |
|---------|-----|--------|------------|
<!-- Add entries here: | v0.x.y | abc1234 | one-line reason | workaround text | -->
