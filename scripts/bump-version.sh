#!/usr/bin/env bash
# Bump the client version and cut the release in one step.
#
# Keeps the two version sources in lockstep (enforced by
# tests/test_version_consistency.py): the repo-level VERSION file and the
# odoo-semantic-skills plugin's plugin.json.version. The odoo-semantic-mcp
# plugin versions independently and is left untouched.
#
# It also "cuts" the changelog: the current `## [Unreleased]` heading is dated
# and stamped with the new version, and a fresh empty `## [Unreleased]` is left
# on top. This prevents the drift where a version is bumped but the CHANGELOG is
# not (which is exactly how 2.4.0/2.4.1 shipped without changelog sections).
#
# Usage:
#   scripts/bump-version.sh patch     # x.y.Z -> x.y.(Z+1)
#   scripts/bump-version.sh minor     # x.Y.z -> x.(Y+1).0
#   scripts/bump-version.sh major     # X.y.z -> (X+1).0.0
#   scripts/bump-version.sh 2.4.2     # set an explicit version
#
# Pick the level by impact: patch = fixes / internal refactors / docs;
# minor = backward-compatible features; major = breaking changes.
set -euo pipefail

level="${1:?usage: bump-version.sh <major|minor|patch|X.Y.Z>}"
root="$(git rev-parse --show-toplevel)"
version_file="$root/VERSION"
plugin_json="$root/plugins/odoo-semantic-skills/.claude-plugin/plugin.json"
changelog="$root/CHANGELOG.md"

cur="$(tr -d '[:space:]' < "$version_file")"
if ! [[ "$cur" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "ERROR: VERSION ('$cur') is not MAJOR.MINOR.PATCH" >&2
  exit 1
fi
IFS=. read -r MA MI PA <<< "$cur"

case "$level" in
  major) new="$((MA + 1)).0.0" ;;
  minor) new="${MA}.$((MI + 1)).0" ;;
  patch) new="${MA}.${MI}.$((PA + 1))" ;;
  *.*.*)
    if [[ "$level" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then new="$level";
    else echo "ERROR: explicit version must be X.Y.Z" >&2; exit 1; fi ;;
  *) echo "ERROR: level must be major|minor|patch or an explicit X.Y.Z" >&2; exit 1 ;;
esac

date_str="$(date +%F)"

# 1) VERSION file
printf '%s\n' "$new" > "$version_file"

# 2) odoo-semantic-skills plugin.json (top-level "version" only, format preserved)
python3 - "$plugin_json" "$new" <<'PY'
import re, sys
path, new = sys.argv[1], sys.argv[2]
s = open(path, encoding="utf-8").read()
s2, n = re.subn(r'("version"\s*:\s*")[0-9]+\.[0-9]+\.[0-9]+(")', rf'\g<1>{new}\g<2>', s, count=1)
assert n == 1, f"expected exactly one top-level version in {path}, replaced {n}"
open(path, "w", encoding="utf-8").write(s2)
PY

# 3) regenerate version-derived artifacts (gemini-extension.json embeds the version)
python3 "$root/plugins/odoo-semantic-skills/generator/gen_mcp_manifests.py" >/dev/null

# 4) CHANGELOG: cut [Unreleased] -> [new] - date, leave a fresh empty [Unreleased]
python3 - "$changelog" "$new" "$date_str" <<'PY'
import sys
path, new, date = sys.argv[1], sys.argv[2], sys.argv[3]
s = open(path, encoding="utf-8").read()
needle = "## [Unreleased]\n"
assert needle in s, "no '## [Unreleased]' heading in CHANGELOG.md"
replacement = f"## [Unreleased]\n\n## [{new}] - {date}\n"
open(path, "w", encoding="utf-8").write(s.replace(needle, replacement, 1))
PY

echo "bumped $cur -> $new"
echo "  VERSION, odoo-semantic-skills/plugin.json, generated manifests, CHANGELOG cut to [$new] - $date_str"
echo "Next: review 'git diff', then commit. odoo-semantic-mcp version is independent (untouched)."
