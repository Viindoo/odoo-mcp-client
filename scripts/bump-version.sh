#!/usr/bin/env bash
# Bump the client version and cut the release in one step.
#
# Keeps the two version sources in lockstep (enforced by
# tests/test_version_consistency.py): the repo-level VERSION file and the
# odoo-ai-agents plugin's plugin.json.version. The odoo-semantic-mcp
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
#   scripts/bump-version.sh 2.4.2     # set an explicit version (NL-override path)
#   scripts/bump-version.sh auto      # auto-classify the level from the commit range
#   scripts/bump-version.sh auto --dry-run   # preview the suggestion, write nothing
#
# Pick the level by impact: patch = fixes / internal refactors / docs;
# minor = backward-compatible features (incl. a new command/skill/agent);
# major = breaking changes. `auto` applies this policy deterministically by
# reading the commits since VERSION last changed (see classify_auto below).
set -euo pipefail

level="${1:?usage: bump-version.sh <major|minor|patch|auto|X.Y.Z> [--dry-run]}"
dry_run=""
if [[ "${2:-}" == "--dry-run" ]]; then dry_run=1; fi

root="$(git rev-parse --show-toplevel)"
version_file="$root/VERSION"
plugin_json="$root/plugins/odoo-ai-agents/.claude-plugin/plugin.json"
codex_plugin_json="$root/plugins/odoo-ai-agents/.codex-plugin/plugin.json"
changelog="$root/CHANGELOG.md"

cur="$(tr -d '[:space:]' < "$version_file")"
if ! [[ "$cur" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "ERROR: VERSION ('$cur') is not MAJOR.MINOR.PATCH" >&2
  exit 1
fi
IFS=. read -r MA MI PA <<< "$cur"

# classify_auto: emit the SemVer level (major|minor|patch) implied by the commits
# since VERSION was last touched, plus a one-line reason on stderr. The repo's v*
# tags are stale (they lag VERSION badly), so anchor on the commit that last changed
# the VERSION file, NOT on a tag. Tag is only a last-resort fallback.
classify_auto() {
  local anchor range
  anchor="$(git log -1 --format=%H -- "$version_file" 2>/dev/null || true)"
  if [[ -n "$anchor" ]]; then
    range="${anchor}..HEAD"
  else
    local tag
    tag="$(git describe --tags --abbrev=0 --match 'v*' 2>/dev/null || true)"
    if [[ -n "$tag" ]]; then range="${tag}..HEAD"; else range="HEAD"; fi
  fi

  # Breaking marker: a conventional-commit `!` before the colon, or a
  # `BREAKING CHANGE:` / `BREAKING-CHANGE:` footer (the spec treats the hyphen and
  # space forms as synonyms, and REQUIRES the `: ` delimiter - so anchor on it to
  # avoid matching prose that merely starts with the words "BREAKING CHANGE").
  local subj
  while IFS= read -r subj; do
    if [[ "$subj" =~ ^[a-zA-Z]+(\([^\)]+\))?!: ]]; then
      echo "auto: major (breaking commit: $subj)" >&2
      echo "major"; return 0
    fi
  done < <(git log --format=%s "$range" 2>/dev/null)
  local breaking_body
  breaking_body="$(git log --format=%B "$range" 2>/dev/null | grep -m1 -E '^BREAKING[ -]CHANGE: ' || true)"
  if [[ -n "$breaking_body" ]]; then
    echo "auto: major (breaking note: $breaking_body)" >&2
    echo "major"; return 0
  fi

  # Minor: any feat: commit, OR a newly ADDED command/skill/agent file.
  local feat
  feat="$(git log --format=%s "$range" 2>/dev/null | grep -m1 -E '^feat(\([^\)]+\))?:' || true)"
  if [[ -n "$feat" ]]; then
    echo "auto: minor (feature commit: $feat)" >&2
    echo "minor"; return 0
  fi
  # Added (A) files only, as bare paths (--diff-filter=A --name-only), so the
  # directory regex matches the path itself rather than the "A<TAB>path" line.
  # Only meaningful for a two-dot range (<anchor|tag>..HEAD); in the no-anchor
  # "HEAD" fallback `git diff HEAD` would compare the WORKING TREE, not history,
  # so skip the added-file rule there (the feat/breaking subject rules above
  # still run via `git log HEAD`).
  if [[ "$range" == *..* ]]; then
    local added
    added="$(git diff --diff-filter=A --name-only "$range" 2>/dev/null | grep -m1 -E '(^|/)(skills|agents|commands)/' || true)"
    if [[ -n "$added" ]]; then
      echo "auto: minor (new command/skill/agent: $added)" >&2
      echo "minor"; return 0
    fi
  fi

  # Default: patch (fix / perf / refactor / docs / chore / test / style / no commits).
  echo "auto: patch (no feature/breaking change since last VERSION bump)" >&2
  echo "patch"; return 0
}

if [[ "$level" == "auto" ]]; then
  level="$(classify_auto)"
fi

case "$level" in
  major) new="$((MA + 1)).0.0" ;;
  minor) new="${MA}.$((MI + 1)).0" ;;
  patch) new="${MA}.${MI}.$((PA + 1))" ;;
  *.*.*)
    if [[ "$level" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then new="$level";
    else echo "ERROR: explicit version must be X.Y.Z" >&2; exit 1; fi ;;
  *) echo "ERROR: level must be major|minor|patch|auto or an explicit X.Y.Z" >&2; exit 1 ;;
esac

if [[ -n "$dry_run" ]]; then
  echo "dry-run: would bump $cur -> $new (level: $level)"
  echo "No files written. Re-run without --dry-run to apply."
  exit 0
fi

date_str="$(date +%F)"

# 1) VERSION file
printf '%s\n' "$new" > "$version_file"

# 2) odoo-ai-agents plugin.json - both the Claude (.claude-plugin) and Codex
#    (.codex-plugin) manifests, which carry their own top-level "version" and must stay
#    in lockstep with VERSION (gemini-extension.json is regenerated in step 3).
python3 - "$new" "$plugin_json" "$codex_plugin_json" <<'PY'
import re, sys
new, paths = sys.argv[1], sys.argv[2:]
for path in paths:
    s = open(path, encoding="utf-8").read()
    s2, n = re.subn(r'("version"\s*:\s*")[0-9]+\.[0-9]+\.[0-9]+(")', rf'\g<1>{new}\g<2>', s, count=1)
    assert n == 1, f"expected exactly one top-level version in {path}, replaced {n}"
    open(path, "w", encoding="utf-8").write(s2)
PY

# 3) regenerate version-derived artifacts (gemini-extension.json embeds the version)
python3 "$root/plugins/odoo-ai-agents/generator/gen_mcp_manifests.py" >/dev/null

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
echo "  VERSION, odoo-ai-agents/plugin.json, generated manifests, CHANGELOG cut to [$new] - $date_str"
echo "Next: review 'git diff', then commit. odoo-semantic-mcp version is independent (untouched)."
