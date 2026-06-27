<!-- SSOT snippet (self-contained copy for this plugin - a runtime cannot cross-reference
     another plugin's snippet). The single home WITHIN git-toolkit for the chat-output language
     contract. Referenced via ${CLAUDE_PLUGIN_ROOT}/snippets/language-mirroring.md. Edit here only. -->

# Language Mirroring - chat output contract (SSOT for git-toolkit)

The humans using this toolkit work in many languages. They prompt in their own language and they
review gates, plans, and summaries in chat. Mixing English prose into their language makes a gate
hard to review and erodes trust - they approve things they only half-understood.

## The contract

Every piece of CHAT-FACING text the agent emits - gate messages, the destructive human-confirm
prompt, plan summaries, clarifying questions, progress notes, final summaries, and RELAYS of
worker results - mirrors the USER'S language:

1. **Mirror 100% of the prose.** Detect the user's language from their prompts and write all
   sentences in it. Skill and agent bodies are written in English - they are instructions TO you,
   not text to paste. Keep a gate template's STRUCTURE (lines, the confirm options) but translate
   every label and sentence.
2. **Keep verbatim:** code, identifiers, branch/ref/tag/SHA values, file paths, git and `gh`
   commands, tool names (`mcp__plugin_github_github__*`), URLs, version strings, and the literal
   keywords the user must type back (`yes`, `confirm`, `cancel`).
3. **Explain unavoidable technical terms** in plain words in the user's language the first time
   each appears (keep the term, add a short gloss in parentheses).
4. **Relaying worker results:** worker reports arrive in English - translate the human-facing parts
   and keep technical identifiers verbatim. You MAY pass the user's language in a worker brief so
   its summary arrives pre-mirrored.
5. **CHAT ONLY, never code or tool-layer:** this governs chat-facing text exclusively. Commit
   messages, branch names, code, comments, worker briefs, and findings-file contents stay English
   regardless of the user's language, unless the user explicitly asks otherwise.

Building for the audience is the why: the audience of chat output is the human at the screen, in
their language - not the skill author.
