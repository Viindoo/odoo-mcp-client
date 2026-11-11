# OSM-first grounding contract

In Odoo work the ground truth is the Odoo Semantic index (OSM) and the running instance, not
memory: models, fields, methods, CLI flags, asset bundles and design tokens differ per series.

## 1. Verify before you claim

A statement that an Odoo model, field, method, module, edition, CLI flag or design token exists,
has a signature or behaves a certain way is backed by an OSM answer or a source read at the target
version and profile; otherwise it is written as an assumption. Pin the version (and the profile
when known) and pass both on every call under concurrency
(`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § OSM session-pin race). Which tool
answers a question is yours to choose from the tools' own descriptions.

- **Existence is not currency.** A symbol can be present and deprecated. Before you write or
  approve code that calls a core symbol (decorator, mixin, ORM helper, base class, core method),
  confirm its status at the pinned version; a "not found" from the core-API table proves nothing
  either way - cross-check (`${CLAUDE_PLUGIN_ROOT}/snippets/symbol-currency-check.md`).
- **Presence in the index is not presence at runtime.** Field or method presence that depends on
  another module is resolved through the dependency closure, never probed at runtime with
  `hasattr`, a `getattr` default or `try/except AttributeError`
  (`${CLAUDE_PLUGIN_ROOT}/snippets/field-presence-resolution.md`).
- An entity the index does not hold (a local custom module) is read from the local source; the
  rest stays on OSM (`grounded: hybrid`).

### The tree under edit

OSM indexes a branch, not your worktree: it cannot hold an unpushed commit, an uncommitted edit or
the change under review. Let `W` be the modules whose directory is in the run's worktree and that
the diff touches, plus every module the run creates or renames.

| Subject | Source of truth |
|---|---|
| A module in `W`: its manifest, `depends`, fields, methods, views, access rules, data, strings | the files on disk; an OSM answer about it is a baseline at most |
| A module outside `W` | OSM; the checkout on a miss |
| A chain or closure that crosses the boundary (an override chain, an upstream closure, an ORM path through a new field) | assembled by you: disk for the part in `W`, OSM for the rest; a path through a changed field is proven on disk and by a test on an instance, not by the index validators |
| Dependents of a symbol and the tests guarding it | the index gives a lower bound; add a search of the repository's manifests and `tests/` |
| Deprecations, canonical patterns, examples, series conventions | OSM, independent of `W` |

Record the source of each fact as `worktree` or `index`. OSM and disk disagree about a module in
`W`: disk is right and it is not a finding. They disagree about a module outside `W`: the index
lags the branch - record `UNKNOWN` and read the checkout when one is available. Behaviour observed
on an instance built from the worktree outranks both.

## 2. Reuse before you write

Before a non-trivial artifact, find what the series already offers and prefer it: an indexed
pattern or example for backend code, the override point when hooking into existing behaviour, real
component patterns and the series' real design tokens and style origins for frontend
(`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md`). When the index has nothing
relevant, say so, then write.

## 3. Validate before you declare done

- **Backend:** every `@api.depends` path, domain, `related` chain and relational assumption you
  generated passes the index validators for symbols outside `W`; a broken or mismatched result is
  a blocker. The quality gate is the lint-class module set run with the tests
  (`${CLAUDE_PLUGIN_ROOT}/snippets/lint-gate-modules.md`); `lint_check` is a hint, except that a
  `[pattern]` security hit is a finding.
- **Frontend:** verified on the running instance after the assets are rebuilt - tokens resolve and
  the screen matches the mockup (`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md`).
- **CLI:** the flags of an `odoo-bin` command come from the target series (`cli_help`), never from
  another series.

## 4. Fallback: read the source, do not ask the human

OSM unreachable - a refusal, a timeout, a hang or a transport error alike - drops you to the source
at once (`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`): the local addons, or the
official source of the target series, labelled `grounded: local-source`. After repeated timeouts
in a session, stop calling OSM for the rest of it. Memory alone is the last resort, labelled
`grounded: ungrounded`, with the caveat carried into the final artifact. A human is asked only for
a business decision no source encodes.

## 5. The grounding label

Your report carries one line of its own, outside any code fence, for its own work:

    grounded: <value> - <explanation>

`<value>` is the first word after the key: `osm`, `hybrid`, `local-source`, `ungrounded` or
`unknown`, or a tally of `<key>=<n>` over those keys (`osm=3 local-source=1`). `osm`, `hybrid` or
a tally with either above zero claims OSM grounding. Every artifact you write uses the same key
and values. A hook reads the label against your own tool calls: a claim of OSM grounding with no
OSM call blocks your stop until you verify or relabel honestly.
