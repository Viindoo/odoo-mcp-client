# Doc-cluster planning algorithm - schedule multi-module documentation by DAG shape (SSOT)

A multi-module documentation package (user-guide `doc/index.rst` + marketing landing
`static/description/index.html`) is planned, not fanned out flat. Documenting a module while the
modules that EXTEND it are also installed produces polluted, extension-contaminated screenshots; a
flat one-instance-per-module fan-out re-installs shared base deps N times and never dedups. This
file is the single algorithm that turns an in-scope module set into a `doc-plan.yaml`: dependency
CLUSTERS, instance allocation by DAG SHAPE, incremental leaf-first install order, cross-module
dedup, and an inter-instance parallelism schedule.

**Consumers (reference this file, do not restate it):**
- `odoo-doc-planner` agent - the leaf that computes and writes `doc-plan.yaml`.
- `module-packaging.workflow.yaml` `doc-plan` phase - reuses this contract inline.

**Reuse, do not re-derive.** The module-DAG primitive lives in
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-module-graph.md` (OSM
`module_inspect(name=..., method='dependencies', odoo_version=...)` primary, disk `__manifest__['depends']` fallback,
topological sort). This file only adds what to DO with that graph for documentation - the
scheduling semantics are INVERTED versus code-build: code batches the DAG into parallel waves;
doc runs SEQUENTIAL within a dependency path (incremental install on one instance) and PARALLEL
across independent branches and clusters.

**Edge direction convention (same as `odoo-module-graph.md`).** "`X depends Y`" means X requires
Y; Y is the deeper leaf-dependency and is installed FIRST. Leaf-dependency-first throughout.

---

## Algorithm

Input = the in-scope module set with per-module `depends_in_scope` (the subset of
`__manifest__['depends']` that is also in scope) and `has_ondisk_doc`, either from the
`odoo-doc-scoper` scope block (doc-only standalone path) or from an approved design DAG
(full-lifecycle path). Output = `doc-plan.yaml`.

### 1. Build the in-scope sub-graph

Restrict edges to the in-scope set (`depends_in_scope`); edges to out-of-scope modules are upstream
context only, never in-set ordering edges. Compute per `odoo-module-graph.md`. OSM-verify the disk
edges opportunistically (trust-but-verify) with the CONCRETE Odoo version - never `'auto'` (the pin
is per-API-key and racy, `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` "OSM
version-pin race").

### 2. Connected components = CLUSTERS

Each connected component of the sub-graph (undirected connectivity) is one cluster. Independent
clusters carry no cross edges and schedule fully in parallel (subject to W, step 6).

### 3. Topological order within each cluster (leaf-dependency first)

Order every cluster so the deepest dependency is installed and doc'd first and each module is doc'd
only after its in-scope deps - never before a module that extends it.

### 4. Instance allocation by DAG STRUCTURE (branch-aware, NOT flat 1-per-cluster)

Allocate instances by the SHAPE of the sub-graph. Three rules compose (default
`purity: strict-branch`):

- **(a) Linear chain -> ONE instance, incremental.** A path `mod_c <- mod_b <- mod_a` (each extends
  the previous) installs on ONE persistent instance leaf-first: install mod_c, doc mod_c ({mod_c});
  install mod_b, doc mod_b ({mod_c,mod_b}); install mod_a, doc mod_a. At each doc step ONLY the
  module + its deps are installed - no reverse-dependent yet -> pure. Base reused, never
  re-installed.
- **(b) Independent branches -> SEPARATE instance each (STRICT purity).** When a node depends on two
  or more MUTUALLY-INDEPENDENT modules, each independent branch gets its OWN instance so its docs are
  captured on a pure `{branch + its deps}` DB - a sibling branch's menus never leak into the other's
  screenshots. Do NOT co-install independent siblings just because they share a cluster.
- **(c) Convergence node -> REUSE one branch instance + install the FILL.** The node that depends on
  several branches reuses ONE of its branch instances (the one already holding that branch's
  modules) and installs ONLY the still-missing modules (the other branches + the node itself), then
  docs the node on the now-complete DB. The node legitimately needs all its branches, so this is
  pure for the node.

Deeper trees / diamonds recurse: one instance per independent leaf-path, converge inner joins by
reuse+fill bottom-up. `MAX_CLUSTER_MODULES` (knob, default ~6) bounds how large a component may grow
before the planner splits a shared low-level dep for extra parallelism (triggering dedup, step 5).
An optional `purity: fresh-per-module` override allocates one throwaway instance per module for the
paranoid case.

### 5. Dedup - the `doc_owner` map (`doc:true|false`)

Each in-scope module is doc'd exactly ONCE globally. Assign each module one `(instance, install_step)`
doc owner; the owner is where the module sits LOWEST in its topo order (fewest extensions installed
on top = most pure); ties break to the earliest instance in the schedule. Three cases force
`doc:false` (install as a dep, do not re-doc):

- **Shared dependency across branches/clusters** - installed on several instances but doc'd only on
  its owner (`dedup_reason: "duplicate-dep: doc'd in <instance>"`).
- **Convergence fill modules** already doc'd on their own branch instance - `doc:false` in the fill;
  only the convergence node is doc'd there.
- **Already-documented on disk / prior run** - `has_ondisk_doc` true, or a prior run's `index.jsonl`
  covered it -> `doc:false, dedup_reason: existing-on-disk`, UNLESS `REDOC: true` is passed
  (cross-run dedup).

### 6. Parallelism

- **Within a dependency path: SEQUENTIAL** (incremental install on one live instance).
- **Across independent branches and clusters: PARALLEL up to W**, each path on its OWN instance +
  OWN browser family. `W = min(#independent instance-paths, browser-family pool, ephemeral instance
  cap)`. The browser families are exclusive-serial per family (never two workers on one family;
  headless pool vs DISPLAY pool), and the fan-out envelope + instance-lease caps are the
  `concurrency-guard.md` SSOT - reference it, do not restate the numbers. When W=1, all paths
  serialize; the planner records that so the runner reports `DONE_WITH_CONCERNS(W=1: serialized)`.

### 7. Provision flags per install step

Every install step keeps three flags, whose exact names are resolved version-aware via OSM
`cli_help` at runtime (never hardcode a flag spelling):

- **skip-auto-install** - install ONLY the target + its declared deps; do not let Odoo pull in
  `auto_install=True` modules whose menus/fields would pollute the doc (see
  `${CLAUDE_PLUGIN_ROOT}/snippets/demo-data-dynamic.md` for demo seeding; a legitimately-required
  auto-install bridge is added EXPLICITLY to `-i`, never by re-enabling auto-install wholesale).
- **with-demo** - so scenario/screenshot data exists (default-on many series; force where needed).
- **load-language=<csv>** - activate every resolved locale so the UI renders per-locale (English
  mandatory canonical + registry-resolved others).

### 8. Emit `doc-plan.yaml`

Write ONE `doc-plan.yaml` per run in the schema below.

---

## `doc-plan.yaml` schema (SSOT)

Instances live UNDER a cluster (a branching cluster has multiple instances), not one-per-cluster.
`install_step` = position in the CUMULATIVE `-i` set on that instance (step k = {deltas with
install_step <= k}). `doc:true|false` is the dedup switch. `extends_in_scope` (= `depends_in_scope`
∩ the `doc:true` set) drives the cross-reference hint ("Extends `<base>` - see its documentation")
the assembler adds to an extension's doc.

```yaml
run: doc-run-<timestamp>
plan_kind: doc-package                    # distinguishes this from a code-build 3-block plan
plan_source: design-dag | scope           # full-lifecycle reuses the design DAG; standalone resolves from scope
grounding: osm | local-source             # module_inspect vs disk depends fallback
scope_ref: .odoo-ai/packaging/<run>/scope.yaml
clusters:
  # --- cluster c1: LINEAR chain mod_c <- mod_b <- mod_a (each extends the previous) => ONE instance ---
  - cluster_id: c1
    dag: "mod_a depends mod_b depends mod_c"
    instances:
      - instance_id: inst-c1-1
        install_doc_sequence:            # leaf-DEPENDENCY first (deepest dep installed first)
          - {module: mod_c, doc: true, install_step: 1, install_delta: [mod_c], depends_in_scope: [],      extends_in_scope: []}
          - {module: mod_b, doc: true, install_step: 2, install_delta: [mod_b], depends_in_scope: [mod_c], extends_in_scope: [mod_c]}
          - {module: mod_a, doc: true, install_step: 3, install_delta: [mod_a], depends_in_scope: [mod_b], extends_in_scope: [mod_b]}
  # --- cluster c2: BRANCH  mod_a2 depends on TWO independent branches (mod_b2, mod_c2) ---
  - cluster_id: c2
    dag: "mod_a2 depends mod_b2 AND mod_c2; mod_b2, mod_c2 independent"
    instances:
      - instance_id: inst-c2-b           # independent branch 1 -> OWN instance (PURE {mod_b2})
        install_doc_sequence:
          - {module: mod_b2, doc: true, install_step: 1, install_delta: [mod_b2], depends_in_scope: []}
        reused_at: {node: mod_a2}        # convergence reuses THIS instance
      - instance_id: inst-c2-c           # independent branch 2 -> OWN instance (PURE {mod_c2})
        install_doc_sequence:
          - {module: mod_c2, doc: true, install_step: 1, install_delta: [mod_c2], depends_in_scope: []}
    convergence:                         # A reuses ONE branch instance + installs the FILL, then docs A
      - {node: mod_a2, reuse_instance: inst-c2-b, install_fill: [mod_c2, mod_a2],
         doc: true, depends_in_scope: [mod_b2, mod_c2], extends_in_scope: [mod_b2, mod_c2],
         note: "reuse branch-1 (has mod_b2); install missing mod_c2 + mod_a2; doc mod_a2 on {mod_b2,mod_c2,mod_a2}"}
    dedup_skip: []
parallelism:
  within_path: sequential                # incremental install on one instance => serial
  inter_instance_max: <W>                # min(#independent instance-paths, browser-family pool, instance-cap)
  schedule:                              # instances (across all clusters) that run concurrently
    - {batch: 1, instances: [inst-c1-1, inst-c2-b, inst-c2-c]}
    # convergence node mod_a2 runs AFTER branch-1 (inst-c2-b) has doc'd its own modules
provision_cadence:
  incremental: true                      # keep each instance ALIVE; install the next delta between doc steps
  per_step_flags: [skip-auto-install, with-demo, "load-language=<csv>"]   # exact flag spelling resolved via cli_help
  loop: "per instance: for step in install_doc_sequence: install_delta -> doc(if doc:true) -> verify -> commit; then convergence: reuse -> install_fill -> doc"
purity: strict-branch                    # (default) linear paths share; independent branches split; convergence reuses+fills. Override: fresh-per-module
```

---

## Worked examples

- **Linear `A -> B -> C`** (A depends B depends C): 1 instance. Install C, doc C ({C}); install B,
  doc B ({C,B}); install A, doc A ({C,B,A}). Base reused, each doc pure.
- **Branch `A -> {B, C}`** (A depends on B and C; B, C independent): 2 instances.
  `inst-1` install B -> doc B on {B}; `inst-2` install C -> doc C on {C} (parallel with inst-1 up to
  W). Convergence: REUSE `inst-1` (holds B) -> install fill `[C, A]` -> DB `{B, C, A}` -> doc A.
  Result: 2 instances for a 3-module branching cluster; B/C captured pure and in parallel; A once.
- **Dedup `X -> Y -> B`** where B already carries on-disk doc (`has_ondisk_doc`): B is `doc:false`
  (install-only) - only Y and X are doc'd. With `REDOC: true`, B is doc'd again.
