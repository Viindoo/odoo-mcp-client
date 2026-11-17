# Completion Reporting (SSOT)

Your launcher receives your completion report ONCE, as the last act of your dispatch: your
structured result/findings block plus the absolute path of the findings file you produced. Write
the findings file first and finish every other step; the report goes out last.

Working files (a list, a message file, a scratch result) go only in the directory of the findings
file the brief names, else in a directory you create with `mktemp -d` - never in the repository,
beside it, or in any other directory you were not given. Before the report, remove every working
file you created; the findings file and what the brief asked you to produce stay.

How the report goes out:

- **`SubagentHandback` is in your toolset** -> call it once with the FULL report as `message`. Only
  that message reaches your caller; text outside it does not. A second call in the same dispatch
  is refused and nothing you do afterwards amends the report, so call it LAST and ALONE: in a
  message of its own, never beside another tool call, after you have read the result of every
  other call you made - a handback sent beside another call is written before that call's result
  exists.
- **Otherwise** -> your report is the FINAL TEXT of your turn: emit it and stop. That text is what
  your caller receives.

A request your launcher sends you after your report was delivered opens a new dispatch: answer it
with a new `SubagentHandback`, never with plain text, which reaches nobody. Only when that call is
refused as already delivered, send the answer once with the messaging tool - to the id the request
shows as its sender, to `main` when it shows none - and stop. A notice of your own background
work is not a request and needs no new report.

`SubagentHandback` takes no address, so it is not a send. Apart from it and that one case, never
send the report to anyone: no agent can address the context that dispatched it, the sender an
inbound message shows is a type label and not an address, and a send that reports success went
to the root conversation, not to your caller. Keep the report compact: a summary, the status, and the
findings-file path; never diff hunks or file contents.

The only tool call a turn may end on is `SubagentHandback`, alone in its own message;
NEVER end on plain text without the report - either way your caller would have nothing to read.

Ending your turn this way never relaxes any other contract: same safety, scale, and read-only
boundaries, same one scoped job, and the leaves still cannot fan out.
