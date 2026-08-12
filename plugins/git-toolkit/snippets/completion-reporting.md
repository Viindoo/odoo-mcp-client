<!-- SSOT snippet. The single home for how a git-toolkit agent ENDS its turn. Self-contained and
     provider-agnostic. Referenced via ${CLAUDE_PLUGIN_ROOT}/snippets/completion-reporting.md.
     Edit here only. -->

# Completion Reporting (SSOT)

Your completion report is the FINAL TEXT of your turn: your structured result/findings block plus
the absolute path of the findings file you produced. Write the findings file first, then emit the
report and stop. That text is what your caller receives.

Never send the report to anyone. You cannot address the context that dispatched you - no agent can -
and the presence of a messaging tool in your toolset is not an instruction to try. An inbound
message gives you no address either: what it shows as its sender is a type label, and no lookup
exists to turn any name into one. Nor is a send that reports success proof you reached anyone: from a
dispatched context that report goes to the root conversation, which is not waiting for it, while the
caller that is waiting never wakes. Keep the report compact: a summary, the status, and the
findings-file path; never diff hunks or file contents.

NEVER end a turn on a bare tool call or on plain text with no report - that leaves your caller with
nothing to read.

Ending your turn this way never relaxes any other contract: same safety, scale, and read-only
boundaries, same one scoped job, and the leaves still cannot fan out.
