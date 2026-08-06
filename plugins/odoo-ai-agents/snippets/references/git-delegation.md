<!-- Reference material for snippets/git-delegation.md. This file is for humans and authors doing
     repo archaeology - it is never cited from any consumer-facing skill/agent/snippet body (see
     docs/authoring-skills-and-agents.md). Explanation and worked examples only; every decidable
     rule stays in the main file. -->

# Git Delegation Contract - rationale

## Why base-branch resolution never trusts the invoking checkout's ambient HEAD

The confirmed root cause of the owner-reported defect ("if someone has already checked out to a
different branch, the agent gets confused and uses that branch as the base") was a schema defining
`base` as "the principal branch at dispatch" - literally whatever was checked out when the run
started. `git branch --show-current` stays legitimate for diagnostic reads and source-series
inference precisely because THAT use never assigns the read value to `base` - only the assignment
itself reproduces the defect.

## Why a substring match on candidate branch names is banned

A substring match (e.g. matching `17.0-feat-x` because it contains `17.0`) reproduces the exact
confusion the exact-match rule exists to prevent, one level down: a human's feature branch would
qualify as a "candidate" purely for containing the series number, silently becoming eligible to be
resolved as the base.
