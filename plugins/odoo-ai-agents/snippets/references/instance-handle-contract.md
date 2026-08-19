<!-- Reference material for snippets/instance-handle-contract.md. This file is for humans and
     authors doing repo archaeology - it is never cited from any consumer-facing skill/agent/snippet
     body (see docs/authoring-skills-and-agents.md). Explanation and worked examples only; every
     decidable rule stays in the main file. -->

# Instance Handle Contract - rationale

## Why collision is not solved merely by going through `odoo-instance`

The shared/spinup path collides on the same declared/`8069` numbers even when every caller
carries a handle - the shared render target intentionally shares one db+port across many readers.
An ISOLATED lease (a unique db + an allocator-issued pooled port + an owned lease, keyed on
`run_id`) is what prevents a collision outright. The `persist:` values that select between them,
and the parked state a suspended isolated lease sits in, are spelled out only in
`docs/reference/INSTANCE-ALLOCATION.md` §5 - restating them here is how a reference copy ends up
naming three states for a vocabulary that has four.

## The structural backstop's exact scope (belt-and-braces detail)

`scripts/lib/allocator.py`'s `_addons_path_worktree_mismatch` guard (`cmd_acquire`) REFUSES (exit
5) an acquire in `shared`/`ephemeral`/`exclusive` mode whenever the caller's cwd is a linked git
worktree of the SAME repository as a catalog `addons_path` entry at a DIFFERENT checkout path AND
no `--addons-path-override` was passed - the exact "silently defaults to the principal checkout"
shape the worktree-addons carve-out exists to prevent. `readonly` mode is exempt (it never builds,
so there is nothing to mis-verify). The guard never inspects an override's CONTENT, so once ANY
override is present it trusts it unconditionally - no structural guard can verify a caller's true
intent from a value it was simply handed, which is why the dispatcher-side policy step remains the
sole protection for a wrong-but-present override.

## Addons coverage assertion - why "to see what happens" is banned

A suite that loads a different copy of the module than the one being verified is structurally
biased toward green: the test runs, may even pass, and proves nothing about the code under review.
The assertion exists to catch exactly that silent substitution before the run starts, not after.
