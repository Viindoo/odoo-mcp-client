# Language mirroring - chat output contract (SSOT)

The humans using this plugin work in many languages. They prompt in their own
language and review gates, proposals, plans, and summaries in chat. An answer mixing
English prose and unexplained jargon into their language is hard to review and erodes
trust in the gate flow - the human approves things they only half-understood.

## The contract

Every piece of CHAT-FACING text the main agent emits - gate messages, proposals,
plan tables' prose, clarifying questions, progress notes, final summaries, and
RELAYS of subagent results - mirrors the USER'S language:

1. **Mirror 100% of the prose.** Detect the user's language from their prompts
   and write all sentences in it. Skill bodies and templates are written in
   English - they are instructions TO you, not text to paste. When a skill shows
   a gate/proposal template, keep its STRUCTURE (lines, table columns, the
   `(approve / refine / cancel)` options) but translate every label and sentence.
2. **Keep verbatim:** code, identifiers, model/field/module names, file paths,
   CLI commands, tool and skill names, URLs, version strings, and the literal
   keywords the user must type back (`approve`, `refine:`, `cancel`, `yes`).
3. **Explain unavoidable technical terms** in plain words in the user's language
   the first time each appears in a conversation (keep the term, add a short
   plain-language gloss in parentheses). Prefer the plain-language phrasing over
   the jargon thereafter.
4. **Relaying agent results:** subagent reports may arrive in English. Do not
   paste them as-is - translate the human-facing parts and keep the technical
   identifiers verbatim. When dispatching an agent, you MAY pass the user's
   language in the brief so its `summary` field arrives pre-mirrored.
5. **What this does NOT apply to - CHAT ONLY, never code:** this contract
   governs chat-facing text exclusively. Code, comments, docstrings, variable
   and field names, commit messages, plan.md, design docs' technical sections,
   and tool-layer API output stay English regardless of the user's language,
   unless the user explicitly asks otherwise - never write source code or
   docstrings in the user's chat language. The Intent & Business Value section
   of a design doc and any gate SHOWN in chat follow the user's language,
   because their audience is the human approver.

Building for the audience is the why: the audience of chat output is
the human in front of the screen, in their language - not the skill author.
