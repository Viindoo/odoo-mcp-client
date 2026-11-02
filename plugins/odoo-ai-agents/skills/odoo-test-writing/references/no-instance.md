# No instance

With no `INSTANCE_HANDLE` (authoring never waits for one -
`${CLAUDE_PLUGIN_ROOT}/snippets/instance-optional-completion.md`), write the tests and return
`status: NEEDS_NEXT` naming the pending tests at method level:
```
next:
  - skill: odoo-instance
    reason: the tests are written; provision an instance and hand its INSTANCE_HANDLE back so their baseline and break runs can execute - GATE_ROLE node-verify, never the pre-PR lint gate
    inputs: {operation: run-tests, GATE_ROLE: node-verify, series: "<series>", modules: ["<module under test>"], test_tags: "/<module>:<Class>.<method>[,...] - the pending tests only", mode: "<fresh|reuse - optional>"}
    confidence: 0.9
```
Fall back to `BLOCKED` only when provisioning is itself impossible. On an existing database a run
uses `-u <module>`, a fresh one `-i <module>`
(`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § Test run on an existing database - `-i`
vs `-u`), with the instance's own interpreter (`${CLAUDE_PLUGIN_ROOT}/snippets/venv-resolution.md`).
