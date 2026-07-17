#!/usr/bin/env bash
# migrate-project-state.sh - SessionStart guarded one-shot: seed the
# machine-global Tier-2 state root (Problem 3 - namespaced ~/.odoo-ai/, SSOT:
# snippets/state-root-resolution.md) from a legacy project-local ./.odoo-ai/
# tree, if one still exists in the session's working directory.
#
# Thin wrapper around scripts/lib/migrate_project_state.sh - all migration
# logic (tier classification, copy-not-clobber, visual/ split-dispatch) lives
# there; this hook only sources it and calls the one entrypoint function.
#
# Contract: never blocks or slows the session - always exits 0, even on
# internal failure. Fast no-op (single `-d` test, no resolver call, no git
# invocation) when no legacy `.odoo-ai/` exists under $PWD - the common case
# for a project that has fully converged on Tier-2, or one that never had a
# project-local tree to begin with.
set -uo pipefail

_plugin_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)"
_lib="${_plugin_root}/scripts/lib/migrate_project_state.sh"

if [ -n "${_plugin_root}" ] && [ -f "${_lib}" ]; then
  # shellcheck source=../scripts/lib/migrate_project_state.sh
  if . "${_lib}" 2>/dev/null; then
    # Log lines (if any subpath actually migrates) go to stderr only - never
    # stdout, which SessionStart hooks may reserve for structured JSON context
    # injection elsewhere in this hook group.
    migrate_project_state "${PWD}" >&2 || true
  fi
fi

exit 0
