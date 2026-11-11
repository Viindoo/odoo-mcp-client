# Language of chat and of documents

The people using this plugin work in many languages. What a human reads or approves is written in
that human's language; what the machine or another agent reads stays English.

## Which language

1. The language the user writes their requests in.
2. When that does not tell (a bare link, pasted code, a one-word reply): the response language
   configured in Claude Code, which the session-start context states when it is set.
3. Otherwise English.

The main agent passes it down as `USER LANGUAGE` in every brief.

## What follows the user's language

- **Chat**: gates, proposals, clarifying questions, progress notes, summaries and relays of a
  subagent's result. A skill's template is an instruction to you, not text to paste: keep its
  structure (lines, columns, reply options) and translate every label and sentence.
- **Documents a human reads or approves**: the SRS, the design, the plan, the acceptance oracle,
  review and acceptance reports, a survey synthesis, a gap matrix, a requirement list export.

## What stays as it is

- **English**: code, tests, comments, docstrings, identifiers, XML ids, tool-layer output, and the
  working files agents hand each other (worklog, recon, ledgers, JSON state).
- **Its own language**: a translation file, and a module's user documentation in each language it
  ships.
- **The repository's convention**: commit messages and pull request text.
- **Verbatim everywhere**: field and key names of a template, status tokens, model, field and
  module names, file paths, commands, tool and skill names, URLs, versions, and the reply keywords
  the user types back - `approve / refine: [feedback] / cancel` and `approve / skip / cancel`
  (`${CLAUDE_PLUGIN_ROOT}/snippets/vocabulary.md`); `yes` is not one of them.

## Technical terms

The first time an unavoidable technical term appears, keep the term and add a short plain gloss in
the user's language; prefer the plain wording afterwards.
