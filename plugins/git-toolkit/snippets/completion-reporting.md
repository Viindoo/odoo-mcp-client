<!-- SSOT snippet. The single home for how a git-toolkit agent ENDS its turn. Self-contained and
     provider-agnostic. Referenced via ${CLAUDE_PLUGIN_ROOT}/snippets/completion-reporting.md.
     Edit here only. -->

# Completion Reporting (SSOT)

Your launcher receives your completion report ONCE, as the last act of your dispatch: your
structured result/findings block plus the absolute path of the findings file you produced. Write
the findings file first and finish every other step; the report goes out last:

- **`SubagentHandback` is in your toolset** -> call it once with the FULL report as `message`. Only
  that message reaches your caller; text outside it does not. The report is handed over the moment
  the call runs and a second call is refused, so call it LAST - nothing you do afterwards amends
  the report. LAST means in a message of its own: send `SubagentHandback` ALONE, never beside
  another tool call, and only after you have read the result of every other call you made. A
  handback sent in the same message as another call is written before that call's result exists,
  so the report cannot contain it - not the command's output, not whether a verification passed -
  and it is delivered as written, with no way to correct it.
- **Otherwise** -> your report is the FINAL TEXT of your turn: emit it and stop. That text is what
  your caller receives.

`SubagentHandback` takes no address, so it is not a send. Apart from it, never send the report to
anyone. You cannot address the context that dispatched you - no agent can - and the presence of a
messaging tool in your toolset is not an instruction to try. An inbound message gives you no
address either: what it shows as its sender is a type label, and no lookup exists to turn any name
into one. Nor is a send that reports success proof you reached anyone: from a dispatched context
that report goes to the root conversation, which is not waiting for it, while the caller that is
waiting never receives it. Keep the report compact: a summary, the status, and the
findings-file path; never diff hunks or file contents.

NEVER end a turn on a bare tool call (one that carries no report) or on plain text with no report -
that leaves your caller with nothing to read.

Ending your turn this way never relaxes any other contract: same safety, scale, and read-only
boundaries, same one scoped job, and the leaves still cannot fan out.
