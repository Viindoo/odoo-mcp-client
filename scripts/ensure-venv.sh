#!/usr/bin/env bash
# Make sure a working virtualenv exists for the repo's dev tooling, and rebuild it ONLY when the
# CONTENT of requirements.txt changed. Called by the Makefile's `$(VENV)/.stamp` rule.
#
# Usage:
#   scripts/ensure-venv.sh <venv-dir> <requirements-file>
#
# Rules (the reason this is a script and not a Makefile recipe):
#   - Up to date = the venv has a working bin/python AND its .stamp holds the sha256 of the
#     requirements file. A newer mtime with the same content does nothing (a fresh git worktree
#     always has a newer requirements.txt than a venv shared through VENV=...). An empty stamp
#     (written by an older Makefile) counts as unknown, so the venv is rebuilt once.
#   - A rebuild never touches the existing venv until the new one is complete. It is built in the
#     sibling "<venv-dir>.new" (same filesystem, so the swap is a rename), its absolute paths are
#     rewritten to the final location, and only then do two renames put it in place. On any failure
#     the partial sibling is removed and the old venv is left exactly as it was.
#   - `python -m venv` is tried first. A Python that cannot bootstrap pip (no ensurepip) falls back
#     to `uv venv` + `uv pip install` when uv is on PATH; with neither working it fails with a
#     message and the old venv stays.
#   - Nothing is written outside <venv-dir>'s parent: no /tmp, no ambient temp dir.
set -euo pipefail

venv="${1:?usage: ensure-venv.sh <venv-dir> <requirements-file>}"
req="${2:?usage: ensure-venv.sh <venv-dir> <requirements-file>}"

[ -f "$req" ] || { echo "ERROR: requirements file not found: $req" >&2; exit 1; }

# Absolute, symlink-free-enough paths: a venv records the path it was built at.
parent="$(cd "$(dirname "$venv")" 2>/dev/null && pwd)" || {
  echo "ERROR: the parent directory of $venv does not exist" >&2; exit 1; }
name="$(basename "$venv")"
venv="$parent/$name"
new="$venv.new"
old="$venv.old"
stamp="$venv/.stamp"

hash_of() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | cut -d' ' -f1
  else echo "ERROR: need sha256sum or shasum to hash $1" >&2; return 1
  fi
}
want="$(hash_of "$req")"

# A previous run that died between its two renames leaves the old venv at <venv>.old.
if [ ! -e "$venv" ] && [ -d "$old" ]; then mv "$old" "$venv"; fi

venv_works() { [ -x "$1/bin/python" ] && "$1/bin/python" -c 'pass' >/dev/null 2>&1; }

if venv_works "$venv" && [ "$(cat "$stamp" 2>/dev/null || true)" = "$want" ]; then
  exit 0
fi

# ---- rebuild into the sibling ----------------------------------------------------------------
built=""
cleanup() { if [ -z "$built" ]; then rm -rf "$new"; fi; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
rm -rf "$new"

base=""
for c in python3.12 python3.13 python3.14 python3 python; do
  if command -v "$c" >/dev/null 2>&1 \
     && "$c" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3,12) else 1)' 2>/dev/null; then
    base="$c"; break
  fi
done
if [ -z "$base" ]; then
  echo "ERROR: need Python >= 3.12 (tried python3.12/3.13/3.14/python3/python); $venv left as it was" >&2
  exit 1
fi
echo "Building venv with $base ($("$base" --version 2>&1)) into $new"

build_with_venv_module() {
  "$base" -m venv --prompt "$name" "$new" >/dev/null 2>&1 \
    && "$new/bin/python" -m pip --version >/dev/null 2>&1 \
    || return 1
  # pip is there, so a failure from here on is a real install failure, not a bootstrap one.
  "$new/bin/python" -m pip install --quiet --upgrade pip \
    && "$new/bin/python" -m pip install -r "$req" \
    || { echo "ERROR: pip install failed" >&2; exit 1; }
}

build_with_uv() {
  command -v uv >/dev/null 2>&1 || return 1
  echo "$base cannot bootstrap pip in a venv - building with uv instead"
  rm -rf "$new"
  uv venv --quiet --python "$base" --prompt "$name" "$new" \
    && uv pip install --quiet --python "$new/bin/python" -r "$req" \
    || { echo "ERROR: uv venv / uv pip install failed" >&2; exit 1; }
}

build_with_venv_module || build_with_uv || {
  echo "ERROR: could not build a venv: '$base -m venv' cannot bootstrap pip and uv is not on PATH." >&2
  echo "       Install the python venv/ensurepip package (or uv) and retry; $venv left as it was." >&2
  exit 1
}

venv_works "$new" || { echo "ERROR: the new venv has no working bin/python; $venv left as it was" >&2; exit 1; }

# ---- make the new venv correct for its FINAL location ----------------------------------------
# Script shebangs, activate scripts and pyvenv.cfg embed the path the venv was built at.
sed_escape() { printf '%s' "$1" | sed 's/[][\\|&.*^$]/\\&/g'; }
from_re="$(sed_escape "$new")"
to_re="$(printf '%s' "$venv" | sed 's/[\\|&]/\\&/g')"
while IFS= read -r f; do
  rewritten="$f.rewrite"
  sed "s|$from_re|$to_re|g" "$f" > "$rewritten" && cat "$rewritten" > "$f" && rm -f "$rewritten"
done < <(grep -rIlF -- "$new" "$new/bin" "$new/pyvenv.cfg" 2>/dev/null || true)

printf '%s\n' "$want" > "$new/.stamp"

# ---- swap ------------------------------------------------------------------------------------
rm -rf "$old"
if [ -e "$venv" ]; then mv "$venv" "$old"; fi
if ! mv "$new" "$venv"; then
  [ -e "$old" ] && mv "$old" "$venv"
  echo "ERROR: could not move the new venv into place; the old one was restored" >&2
  exit 1
fi
built=1
rm -rf "$old"
echo "venv ready: $venv/bin/python"
