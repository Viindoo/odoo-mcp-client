<!-- Reference material for snippets/instance-handle-contract.md. This file is for humans and
     authors doing repo archaeology - it is never cited from any consumer-facing skill/agent/snippet
     body (see docs/authoring-skills-and-agents.md). Explanation and worked examples only; every
     decidable rule stays in the main file. -->

# Instance Handle Contract - rationale

## Why collision is not solved merely by going through `odoo-instance`

The shared path collides on the same declared/`8069` numbers even when every caller carries a
handle - the shared render target intentionally shares one db+port across many readers. An
ISOLATED lease (`lease_acquire` mode `ephemeral`: a unique db + pooled ports + an owned lease,
keyed on `run_id`) is what prevents a collision outright. The modes themselves are described by the
`lease_acquire` tool; restating them here is how a reference copy drifts from the vocabulary.

## The structural backstop's exact scope (belt-and-braces detail)

`lease_acquire` refuses (`ADDONS_PATH_WORKTREE_MISMATCH`) an acquire in `shared`/`ephemeral`/
`exclusive` mode whenever the caller's `cwd` is a linked git worktree of the SAME repository as a
catalog `addons_path` entry at a DIFFERENT checkout path AND no `addons_path` was passed - the exact
"silently defaults to the principal checkout" shape the worktree-addons carve-out exists to
prevent. `readonly` mode is exempt (it never builds, so there is nothing to mis-verify). The refusal
never inspects a passed `addons_path`'s CONTENT, so once ANY value is present it trusts it - no
structural guard can verify a caller's true intent from a value it was simply handed, which is why
the addons coverage assertion remains the sole protection for a wrong-but-present value.

## Addons coverage assertion - why "to see what happens" is banned

A suite that loads a different copy of the module than the one being verified is structurally
biased toward green: the test runs, may even pass, and proves nothing about the code under review.
The assertion exists to catch exactly that silent substitution before the run starts, not after.

## Why `demo` / `languages_loaded` are read from the database

A handle is often forwarded onto a database another lease built, so the builds one lease recorded
say nothing reliable about what the database holds. The tools read demo and the active languages
from the database itself and fall back to the build records of every lease on it only when it
cannot be read; `facts_source` names which answered. The same read backs the tools' own refusals
(a test build on a demo database where the series loads none, an i18n export without demo or a
language), so an agent plans from the handle and the tool enforces from the database.

## Why one build or export per database

Two Odoo processes installing, updating or exporting on one database at once race on the module
registry and on the files they write. The tools refuse the second job and name the running one,
so parallel workers that share a handle queue behind it instead of freeing the database by
tearing down a lease they do not own.
