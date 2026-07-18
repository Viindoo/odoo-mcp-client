.PHONY: validate test gen gen-check deps-check workflows-check orchestration-check help setup bump bump-dry bump-patch bump-minor bump-major

VENV ?= .venv
PYTHON ?= $(VENV)/bin/python
VENV_STAMP := $(VENV)/.stamp

help:
	@echo "make validate        - validate plugin.json + skill frontmatter + workflows (claude plugin validate + pytest); ENFORCES workflows-check + orchestration-check in strict mode"
	@echo "make test            - run the plugin test suite"
	@echo "make gen             - regenerate skill ## MCP tools sections + IDE snippets + orchestration map"
	@echo "make gen-check       - run gen then assert git diff is empty (CI idempotency check)"
	@echo "make deps-check      - check skill ↔ tool dependencies (no broken/removed tool refs)"
	@echo "make workflows-check - validate all workflows/*.workflow.yaml against the schema (hard rules always fatal; warn-first by default here - set WORKFLOWS_STRICT=1 to also enforce the content rules locally; 'make validate' always runs this strict)"
	@echo "make orchestration-check - lint the capability/contract layer (warn-first by default here - set ORCH_STRICT=1 to enforce locally; 'make validate' always runs this strict)"
	@echo "make setup           - create .venv (Python >= 3.12) and install requirements.txt"
	@echo "make bump            - auto-classify the level from commits since last VERSION bump, then bump"
	@echo "make bump-dry        - preview the auto-classified level + resulting version (writes nothing)"
	@echo "make bump-patch      - bump VERSION + plugin.json + cut CHANGELOG (x.y.Z -> x.y.Z+1)"
	@echo "make bump-minor      - bump minor (x.Y.z -> x.Y+1.0) for backward-compatible features"
	@echo "make bump-major      - bump major (X.y.z -> X+1.0.0) for breaking changes"

# Venv stamp: rebuilt whenever requirements.txt changes so new deps are always
# installed (no stale-venv silent-skip). The build is atomic - on any failure
# the partial venv is removed and the stamp is NOT written, so the next run
# retries instead of trusting a broken venv.
$(VENV_STAMP): requirements.txt
	@base=""; \
	for c in python3.12 python3.13 python3.14 python3 python; do \
	  if command -v $$c >/dev/null 2>&1 && $$c -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3,12) else 1)' 2>/dev/null; then base=$$c; break; fi; \
	done; \
	if [ -z "$$base" ]; then echo "ERROR: need Python >= 3.12 (tried python3.12/3.13/3.14/python3/python)"; exit 1; fi; \
	echo "Creating venv with $$base ($$($$base --version 2>&1))"; \
	rm -rf $(VENV); \
	{ $$base -m venv $(VENV) && \
	  $(VENV)/bin/python -m pip install --quiet --upgrade pip && \
	  $(VENV)/bin/python -m pip install -r requirements.txt; } || \
	  { echo "ERROR: venv setup failed - removing partial $(VENV)"; rm -rf $(VENV); exit 1; }
	@touch $(VENV_STAMP)

setup: $(VENV_STAMP)
	@echo "venv ready: $(PYTHON)"

# Structural validation: official CLI check (if available) + our schema/format tests.
# ENFORCING (CI-gating): both content lints below are invoked with --strict, so a genuine
# rule-11/12 (workflows) or rule-5/8 (orchestration) finding fails `make validate` outright.
# For warn-only local iteration while migrating new content, run the standalone
# `make workflows-check` / `make orchestration-check` targets instead (those stay warn-first
# by default; opt into their own strict mode with WORKFLOWS_STRICT=1 / ORCH_STRICT=1).
validate: $(VENV_STAMP)
	@command -v claude >/dev/null 2>&1 && { \
		claude plugin validate plugins/odoo-ai-agents && \
		claude plugin validate plugins/odoo-semantic-mcp && \
		claude plugin validate plugins/git-toolkit; \
	} || \
		echo "(claude CLI not found - skipping 'claude plugin validate'; running pytest checks)"
	$(PYTHON) -m pytest tests/test_plugin_schema.py tests/test_skill_format.py -q
	$(PYTHON) plugins/odoo-ai-agents/generator/check_workflows.py --strict
	$(PYTHON) plugins/odoo-ai-agents/generator/check_orchestration.py --strict

# Workflow schema validator: assert all *.workflow.yaml files conform to the contract. Hard
# rules (1-10) are always fatal; the WARN-FIRST content rules (11-12) print but exit 0 by
# default - set WORKFLOWS_STRICT=1 to promote them to fatal too (same pattern as
# orchestration-check's ORCH_STRICT). `make validate` always runs this checker strict
# regardless of this env var - use this target directly for warn-only local iteration.
workflows-check: $(VENV_STAMP)
	$(PYTHON) plugins/odoo-ai-agents/generator/check_workflows.py $(if $(WORKFLOWS_STRICT),--strict,)

test: $(VENV_STAMP)
	$(PYTHON) -m pytest tests/ -q

# SSOT generator: read generator/server-surface.json → emit skill sections + snippets + orchestration map.
# Also regenerates Codex CLI + Gemini CLI MCP manifests from .mcp.json SSOT.
gen: $(VENV_STAMP)
	$(PYTHON) plugins/odoo-ai-agents/generator/gen_surface.py
	$(PYTHON) plugins/odoo-ai-agents/generator/gen_mcp_manifests.py

# CI idempotency check: gen must produce zero diff on a clean tree.
gen-check: gen
	@dirty="$$(git status --porcelain)"; \
	if [ -n "$$dirty" ]; then \
		echo "ERROR: make gen produced uncommitted changes (incl. new untracked artifacts) - commit the generated output."; \
		echo "$$dirty"; \
		exit 1; \
	fi

# Dependency check: assert all skill ↔ tool refs are valid (live, not removed).
deps-check: $(VENV_STAMP)
	$(PYTHON) plugins/odoo-ai-agents/generator/check_deps.py

# Orchestration/contract lint: spawn-class coverage, OSM-first + design-system + instance
# references, spawn-truth, no-hardcode/no-leak. WARN-FIRST by default here (exits 0); set
# ORCH_STRICT=1 to enforce (exits 1 on any finding) for local iteration. `make validate`
# always runs this checker strict regardless of this env var.
orchestration-check: $(VENV_STAMP)
	$(PYTHON) plugins/odoo-ai-agents/generator/check_orchestration.py $(if $(ORCH_STRICT),--strict,)

# Version bump + release cut. Keeps VERSION and the odoo-ai-agents
# plugin.json in lockstep (enforced by tests/test_version_consistency.py) and
# stamps the CHANGELOG. Pick the level by impact: patch = fix/refactor/docs,
# minor = backward-compatible feature (incl. a new command/skill/agent),
# major = breaking change. `bump` applies this policy automatically; `bump-dry`
# previews it without writing. In an AI session, if a human names a specific
# version/level in natural language, run `scripts/bump-version.sh <that>` instead.
bump:
	./scripts/bump-version.sh auto
bump-dry:
	./scripts/bump-version.sh auto --dry-run
bump-patch:
	./scripts/bump-version.sh patch
bump-minor:
	./scripts/bump-version.sh minor
bump-major:
	./scripts/bump-version.sh major
