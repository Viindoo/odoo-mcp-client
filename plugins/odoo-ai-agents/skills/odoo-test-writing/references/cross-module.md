# Cross-module assertions

- **Cross-module assertions.** A test that asserts behavior contributed by ANOTHER module
  must be staged into the post-install phase - the only moment the whole node is visible - with the
  mechanism the target series ships (`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` row 8).
  Host it in the last module of the node's dependency order; a node whose modules share no
  `depends` edge has no "last module", so host it in the primary module. A `KeyError` on a symbol
  you know exists there is this staging bug, not a code defect.
