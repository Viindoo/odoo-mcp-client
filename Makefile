.PHONY: validate test help

help:
	@echo "make validate  - validate plugin.json + skill frontmatter (claude plugin validate + pytest)"
	@echo "make test      - run the plugin test suite"

# Structural validation: official CLI check (if available) + our schema/format tests.
validate:
	@command -v claude >/dev/null 2>&1 && claude plugin validate . || \
		echo "(claude CLI not found — skipping 'claude plugin validate'; running pytest checks)"
	python3 -m pytest tests/test_plugin_schema.py tests/test_skill_format.py -q

test:
	python3 -m pytest tests/ -q
