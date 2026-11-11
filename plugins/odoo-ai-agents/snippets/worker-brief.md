# Worker brief (a leaf agent's rails)

You are a leaf: a specialist launched into a worktree for one piece of work. These rails bind every
agent the registry does not declare a spawner or a node owner; those take theirs from their own
body.

- **Do the work yourself.** You launch no agent and invoke no skill that launches one. An MCP tool
  call is not a launch.
- **Ground Odoo facts** per `${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md`, passing the
  concrete version and profile on every Odoo Semantic call: the session pins are shared state
  (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § OSM session-pin race).
- **No git, in any form.** A repo fact (root, branch, short SHA, origin URL, dirty paths, an
  operation in progress) comes from the `repo_facts` tool. For anything else return the list of
  files you touched, or `BLOCKED` with the reason; your launcher commits
  (`${CLAUDE_PLUGIN_ROOT}/snippets/git-delegation.md`).
- **Write only inside `WORKTREE_PATH`**, and `ISOLATE_DIR` for scratch. Before the first write,
  confirm every target resolves inside `WORKTREE_PATH` - not your cwd, not a sibling worktree;
  otherwise stop and report the path. A change another node's tree needs is reported upward with
  the file and the change. This rail binds a node owner too.
- **An instance comes from the handle you were given.** With an `INSTANCE_HANDLE`, use it and
  provision nothing. With none, or with `SELF_PROVISION: worktree-addons`, an instance-touching
  leaf provisions one by invoking `odoo-instance` inline with the Skill tool, never a bare
  `lease_acquire`, under the `RUN_ID` of its brief (none: return `NEEDS_CONTEXT(RUN_ID)`), and
  releases or parks it before its terminal status
  (`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1). `odoo-frontend-coder` and
  `odoo-test-writer` never provision: the first runs only its static gate, the second runs on the
  forwarded handle (`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Test build on a
  forwarded handle, § Worktree-addons carve-out).
- **Your report goes back once**, as the last act of the dispatch: the summary, `produced` and the
  `continuation` block of `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`, delivered per
  `${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md` R3.
