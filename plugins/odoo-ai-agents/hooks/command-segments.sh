#!/usr/bin/env bash
# command-segments.sh - SSOT for turning ONE `tool_input.command` string into the list of LOGICAL
# simple commands a PreToolUse detector may reason about. Sourced (never executed) by the two
# PreToolUse hard denies - hooks/block-coordinator-code-write.sh and
# hooks/block-unowned-lease-mutation.sh - which previously each carried their own copy of a
# one-line `sed` splitter plus a comment claiming the other one matched. It did, and so did the
# three defects below.
#
# WHAT IT FIXES, and why each half is load-bearing:
#
#   1. BACKSLASH CONTINUATIONS ARE JOINED FIRST. A command written across two physical lines with
#      a trailing `\` is ONE command. The old splitters read it as two, which broke BOTH
#      directions at once:
#        - false DENY: `allocator.py release <tok> \` + `--run-id <id>` put the verb and its owner
#          flag in different segments, so the ownership arm saw a release naming no owner and
#          refused a lease the caller genuinely owned.
#        - false PASS: `... release <tok> --run-id <id> \` + `--force` put the override flag in a
#          segment carrying no allocator token at all, so the override arm never looked at it. A
#          subagent was one newline away from `--force-forget` on a live lease.
#      The same split silently disarmed the coordinator source-write detectors whose regex is
#      end-anchored (`cp`/`mv`/`install`/`rsync`) or needs the verb and the path together
#      (redirect, `tee`): a two-line `cp src.py dst.py` matched nothing.
#
#   2. A HEREDOC BODY IS DATA, NOT COMMAND TEXT - unless it is fed to an interpreter. Appending a
#      worklog entry with `cat >> worklog.md <<'EOF' ... EOF` put the ENTIRE prose body into
#      `tool_input.command`, so an agent describing WHY it had been blocked was blocked again for
#      naming the path in its own report, and the refusal interpolated the path from the prose
#      rather than the `.md` actually being written. Bodies are therefore dropped - but ONLY when
#      the introducing command is not one that EXECUTES its stdin (`bash`, `sh`, `python`, `node`,
#      `ruby`, `perl`, `env`, `eval`, `xargs`). `bash <<'EOF' ... EOF` really does run its body, so
#      that body stays visible to the detectors.
#
#   3. AN OPERATOR INSIDE QUOTES IS NOT A SEPARATOR. `;`, `&&`, `||`, `|` and `&` split a command
#      only OUTSIDE `'...'` and `"..."`. Splitting inside them tore a single interpreter command in
#      half, and that ran in both directions:
#        - false PASS, a real guard BYPASS: `python3 -c "import pathlib;
#          pathlib.Path('addons/m/models/sale.py').write_text('x')"` split at the quoted `;`, so
#          the half carrying `write_text` no longer carried a `python` token and the interpreter
#          detector never looked at it. A coordinator could write production source through it.
#        - false DENY: `--reason "a && b"` split mid-argument, and a `release` whose `--run-id`
#          followed the quoted operator lost its owner flag.
#      Reported by a peer session that hit the false-deny face of the same detector during a
#      forward-port adapt.
#
#   4. PORTABLE, AND `>&` IS NOT A SEPARATOR. The old splitter used `sed -E 's/.../\n/g'`, whose
#      `\n` replacement is GNU-only: on BSD/macOS sed it emits a literal `n`, silently degrading
#      both gates to whole-command matching. This uses POSIX awk. It also protects the stream-dup
#      operator, so `2>&1` is no longer split into `2>` and `1`.
#
# CONTRACT: `_logical_segments` reads the command on stdin and prints ONE logical simple command
# per line, blank lines omitted. Splitting stays on `||`, `&&`, `;`, `|`, `&` so a flag can never
# be borrowed from a NEIGHBOURING command (`allocator.py release $T && echo --run-id`) and an
# end-of-command anchor stays meaningful.
#
# RESIDUALS - stated, not papered over. This function makes segments; it does not resolve a shell.
#   - A body fed to an interpreter heredoc (`bash <<EOF`) is kept as text, so the detectors see it,
#     but it is not parsed as the script it is.
#   - Quote tracking is lexical, not a shell parse: it does not resolve `$(...)`, `${VAR}` or a
#     nested quoting level a real shell would re-scan.
#   - `$(...)`, `${VAR}`, `eval` and a command assembled inside a script the line only invokes stay
#     outside every detector's reach, exactly as each gate's own header already records.

# Defined with a leading underscore and no side effects: sourcing this file must not alter the
# caller's `set -uo pipefail`, exit status, or any variable it did not name.
_CMDSEG_AWK=$(cat <<'AWK'
function is_interp(s) {
  return (s ~ /(^|[ \t;&|(=])(bash|sh|zsh|ksh|dash|python[0-9.]*|node|ruby|perl|php|env|eval|xargs)([ \t]|$)/)
}
{
  line = $0
  if (skip) {
    t = line
    sub(/^[ \t]+/, "", t)
    sub(/[ \t]+$/, "", t)
    if (t == delim) { skip = 0 }
    next
  }
  buf[++n] = line
  if (match(line, /<<-?[ \t]*("[^"]+"|'[^']+'|[A-Za-z_][A-Za-z0-9_]*)/)) {
    d = substr(line, RSTART, RLENGTH)
    sub(/^<<-?[ \t]*/, "", d)
    gsub(/["']/, "", d)
    pre = substr(line, 1, RSTART - 1)
    if (!is_interp(pre)) { delim = d; skip = 1 }
  }
}
# Replace every UNQUOTED operator with a newline, character by character. A regex cannot do this:
# it has no quote state, so it cannot tell the `;` in `-c "a; b"` from the one in `a; b`.
function split_unquoted(s,    i, c, nxt, q, out) {
  q = ""
  out = ""
  for (i = 1; i <= length(s); i++) {
    c = substr(s, i, 1)
    nxt = substr(s, i + 1, 1)
    if (q != "") {
      # Inside "..." a backslash escapes the next character; inside '...' it does not.
      if (q == "\"" && c == "\\") { out = out c nxt; i++; continue }
      if (c == q) { q = "" }
      out = out c
      continue
    }
    if (c == "'" || c == "\"") { q = c; out = out c; continue }
    if (c == "\\") { out = out c nxt; i++; continue }
    if (c == ">" && nxt == "&") { out = out ">&"; i++; continue }   # stream dup, not a separator
    if (c == "|" && nxt == "|") { out = out "\n"; i++; continue }
    if (c == "&" && nxt == "&") { out = out "\n"; i++; continue }
    if (c == ";" || c == "|" || c == "&") { out = out "\n"; continue }
    out = out c
  }
  return out
}

END {
  m = 0
  cur = ""
  for (i = 1; i <= n; i++) {
    l = buf[i]
    k = 0
    j = length(l)
    while (j > 0 && substr(l, j, 1) == "\\") { k++; j-- }
    if (k % 2 == 1) { cur = cur substr(l, 1, length(l) - 1) " "; continue }
    cur = cur l
    out[++m] = cur
    cur = ""
  }
  if (cur != "") { out[++m] = cur }
  for (i = 1; i <= m; i++) {
    s = split_unquoted(out[i])
    c = split(s, parts, "\n")
    for (p = 1; p <= c; p++) {
      if (parts[p] ~ /[^ \t]/) { print parts[p] }
    }
  }
}
AWK
)

_logical_segments() { awk "$_CMDSEG_AWK"; }
