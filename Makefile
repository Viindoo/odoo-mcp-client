.PHONY: validate test gen gen-check deps-check help

help:
	@echo "make validate  - validate plugin.json + skill frontmatter (claude plugin validate + pytest)"
	@echo "make test      - run the plugin test suite"
	@echo "make gen       - regenerate routing matrix + skill ## MCP tools sections + IDE snippets"
	@echo "make gen-check - run gen then assert git diff is empty (CI idempotency check)"
	@echo "make deps-check - check skill ↔ tool dependencies (no broken/removed tool refs)"

# Structural validation: official CLI check (if available) + our schema/format tests.
validate:
	@command -v claude >/dev/null 2>&1 && claude plugin validate . || \
		echo "(claude CLI not found — skipping 'claude plugin validate'; running pytest checks)"
	python3 -m pytest tests/test_plugin_schema.py tests/test_skill_format.py -q

test:
	python3 -m pytest tests/ -q

# SSOT generator: read generator/server-surface.json → emit routing matrix + skill sections + snippets.
gen:
	python3 generator/gen_surface.py

# CI idempotency check: gen must produce zero diff on a clean tree.
gen-check: gen
	@git diff --exit-code || \
		(echo "ERROR: make gen produced uncommitted changes — update generator/server-surface.json and commit the output." && exit 1)

# Dependency check: assert all skill ↔ tool refs are valid (live, not removed).
deps-check:
	python3 generator/check_deps.py
