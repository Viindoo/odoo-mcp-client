<!-- SSOT snippet: what an agent reads before it acts and before it asks (ODOO-AI-ETHOS #2),
     per class of work. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/read-before-act.md. -->

# Read before act, read before ask

Snippet path prefix below: `${CLAUDE_PLUGIN_ROOT}/snippets/`.

## 1. The reading map - just in time, once per session

Before the first action of a class, read its row. Read only the rows of the classes the request
holds (a docs request reads no coding guideline). A file already read this session is applied from
context; a later step that names it is satisfied by that read. After a context compaction - a
summary at the head of the context, or the plugin's compaction notice - the files read are gone
except the five most recent: re-read the rows of the class in progress before its next write, and
the exact text of any file a decision depends on.

| Class of work | Read first |
|---|---|
| Any Odoo code (write, review, debug, adapt) | `${CLAUDE_PLUGIN_ROOT}/skills/_shared/coding_guidelines/<series>/INDEX.md` and every file its "By file type" row names for the file types touched; `odoo-platform-design-principles.md` |
| Module or cluster upgrade to a higher series | `upg-conventions.md`; `odoo-platform-design-principles.md` § Migrations are decided last |
| Forward-port (code or docs) | `fp-merge-absorption.md`, `fp-installable-false.md` |
| A design, a plan, an acceptance oracle or a QA pass | `odoo-platform-design-principles.md` § 0 |
| Tests | `test-sensitivity-contract.md`, `test-scope-contract.md`, `odoo-platform-design-principles.md` § 0 |
| Docs that ship in a module | `public-docs-contract.md`, `${CLAUDE_PLUGIN_ROOT}/skills/odoo-doc-illustration/references/doc-artifacts.md`, `module-doc-references.md`, `rst-validity-contract.md` |
| Docs-site pages | `public-docs-contract.md`, `${CLAUDE_PLUGIN_ROOT}/skills/odoo-doc-site/references/site-row.md` and `page-plan.md` |
| Marketing copy, App Store page | `public-docs-contract.md`, `${CLAUDE_PLUGIN_ROOT}/skills/odoo-content-draft/references/buyer-profile.md`, `artifact-voice.md` |
| A live instance | `${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-LIFECYCLE.md` § Decision tree |
| Any git need | `git-delegation.md` |
| Launching an agent | `dispatch-brief.md`; `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Model-tier selection |

## 2. Before a question to a human

1. Search the decision's keywords in `snippets/`, `skills/_shared/` and the owning skill's
   `references/`, then the design, the worklog and the source.
2. A rule that settles the decision is applied and cited in the worklog; it is never asked.
3. A question that survives names the rule read, or `no rule found: <paths searched>`, and follows
   the question shape of ODOO-AI-ETHOS #2 (context, affected roles, modules and scope, closed
   options with trade-offs, a recommendation, the default on no answer).
4. The answer settles the question asked. Record it with the rule it refines; never widen it to a
   module, a phase or a rule the question did not name. An answer that contradicts a written rule is
   flagged to the human before it is applied.

## 3. Before writing an artifact

Search for an existing one first (the module tree, the shared documentation cache, the docs site,
earlier drafts under the state root): update it or reuse it; never a second copy of the same
thing (ODOO-AI-ETHOS #3, #11).
