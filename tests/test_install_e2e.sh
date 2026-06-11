#!/usr/bin/env bash
#
# End-to-end install smoke test.
#
# Installs Claude Code, registers the Viindoo marketplace, installs the
# odoo-ai-agents plugin from it, and asserts the install succeeded. Designed for
# the GitHub Actions matrix (Ubuntu / macOS) — it touches the network and
# installs a global npm package, so it is NOT part of the default `make test`.
#
# Hard assertions: plugin installs and is listed.
# Soft assertion : skill count is reported (warns but does not fail on CLI format drift).
set -euo pipefail

echo ">> installing claude-code"
npm install -g @anthropic-ai/claude-code@latest

echo ">> registering marketplace"
claude plugin marketplace add Viindoo/claude-plugins --scope user

echo ">> installing plugin"
claude plugin install odoo-ai-agents@viindoo-plugins --scope user

echo ">> asserting plugin is listed"
if ! claude plugin list | grep -q 'odoo-ai-agents'; then
  echo "FAIL: odoo-ai-agents not found in 'claude plugin list'"
  exit 1
fi

echo ">> checking skill count (soft)"
info="$(claude plugin info odoo-ai-agents 2>/dev/null || true)"
# Meaningful floor: the plugin ships >=20 skills, so a bare "0 skills" or a
# single-digit count signals a broken install and must trip the WARN. We match
# >=20 (two-or-more digits, first group >= 20) while keeping this SOFT - it
# warns but never fails the e2e, since the exact CLI wording may still drift.
if printf '%s' "$info" | grep -Eq '(2[0-9]|[3-9][0-9])[[:space:]]+skills'; then
  echo "OK: skill count reported (>=20)"
else
  echo "WARN: could not confirm a '>=20 skills' count from 'claude plugin info'" \
       "output (CLI format may differ, or the install is incomplete);" \
       "install + listing checks passed."
fi

echo ">> e2e install OK"
