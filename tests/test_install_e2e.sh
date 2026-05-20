#!/usr/bin/env bash
#
# End-to-end install smoke test.
#
# Installs Claude Code, registers the Viindoo marketplace, installs the
# odoo-semantic plugin from it, and asserts the install succeeded. Designed for
# the GitHub Actions matrix (Ubuntu / macOS) — it touches the network and
# installs a global npm package, so it is NOT part of the default `make test`.
#
# Hard assertions: plugin installs and is listed.
# Soft assertion : skill count is ~15 (warns but does not fail on CLI format drift).
set -euo pipefail

echo ">> installing claude-code"
npm install -g @anthropic-ai/claude-code@latest

echo ">> registering marketplace"
claude plugin marketplace add Viindoo/claude-plugins --scope user

echo ">> installing plugin"
claude plugin install odoo-semantic@viindoo-plugins --scope user

echo ">> asserting plugin is listed"
if ! claude plugin list | grep -q 'odoo-semantic'; then
  echo "FAIL: odoo-semantic not found in 'claude plugin list'"
  exit 1
fi

echo ">> checking skill count (soft)"
info="$(claude plugin info odoo-semantic 2>/dev/null || true)"
if printf '%s' "$info" | grep -Eq '15[[:space:]]+skills'; then
  echo "OK: 15 skills reported"
else
  echo "WARN: could not confirm '15 skills' from 'claude plugin info' output" \
       "(CLI format may differ); install + listing checks passed."
fi

echo ">> e2e install OK"
