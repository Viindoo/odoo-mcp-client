# Odoo Failure Modes - by-layer symptom -> root-cause -> localize catalog (SSOT)

> Shared grounding doc for the debug front-door (`odoo-debug`) and its specialist agents. It maps
> the recurring Odoo failure modes per layer to their usual root causes and the OSM tool that
> localizes them, so a debug run starts from known territory instead of from scratch. This is the
> stable-knowledge half; any concrete signature / token / field is version-specific - confirm it
> for the target version via OSM (`set_active_version` first) before relying on it. Skills/agents
> cross-reference this doc; they do not duplicate it.
>
> Each row is: **symptom -> likely root cause -> how to localize**. Use it to pick a falsifiable
> hypothesis (see `debug-method.md` step 3), not as a list of fixes to apply blindly.

---

## Layer: Python / ORM (most common)

| Symptom | Likely root cause | Localize with |
|---|---|---|
| Computed field never updates | `@api.depends` missing/incorrect dependency; ORM cache holds stale value | `model_inspect` (field + depends), `resolve_orm_chain`; toggle by editing a dependency and re-reading |
| `Expected singleton: model(2,)` | Field/attr accessed on a recordset of >1 record (loop missing) | read the traceback frame; `model_inspect` the method |
| `write`/`create` side effects wrong or doubled | wrong assumption about hook order (create vs write vs compute vs onchange vs constraint) | `find_override_point` for the method; check `super()` placement |
| Stale value after write | reading through `env.cache` before invalidation | confirm by `invalidate_recordset()`/`recompute()` then re-read |
| `KeyError` / missing field at runtime | field defined in a module not installed / wrong module load order | `module_inspect` (models + depends); `entity_lookup` |
| ORM call inside a loop (slow/limit) | N+1 - per-record query instead of batch read/write | `resolve_orm_chain`; see Performance layer |
| Override never runs | wrong `_inherit`/`_name`, or super-chain bypassed | `find_override_point` (override chain + anti-patterns) |
| Runtime presence probe (`hasattr(rec,'f')` / `getattr(rec,'f',default)` / `try…except AttributeError`) used instead of direct access | masks one of: (1) lookup-gap - existence never OSM-verified; (2) wrong ORM path - field lives on a related model; (3) missing-depends - field's module not in `depends` closure | `model_inspect` (field + declaring module) + `entity_lookup` (confirm real model/hop) + `module_inspect(method='dependencies', odoo_version='auto')` (walk dep closure); see `${CLAUDE_PLUGIN_ROOT}/snippets/field-presence-resolution.md` |

Tools: `model_inspect`, `resolve_orm_chain`, `find_override_point`, `lookup_core_api`,
`validate_depends`, `validate_domain`, `validate_relation`, `find_examples`.

## Layer: XML / Views / Data

| Symptom | Likely root cause | Localize with |
|---|---|---|
| `ParseError` on module load | field in view not on model; bad `eval`/domain; malformed arch | traceback names file+line; `model_inspect` to confirm the field exists |
| External id not found | `ref()` to a record from an uninstalled/unordered module | `module_inspect` (data + depends); grep the xml id |
| View inherit does nothing | wrong `inherit_id` xpath / position; expr no longer matches | `module_inspect` (views); diff the target arch |
| Record rule/menu missing | data file not in `__manifest__.py` data list, or wrong order | `module_inspect` (manifest summary) |

## Layer: JS / OWL / QWeb / SCSS (frontend runtime) - BROWSER

> This layer needs live browser evidence (console/network/DOM) AND code grounding. It is the
> exclusive-serial leg: never run two browser-driving agents at once (shared Chromium/session).

| Symptom | Likely root cause | Localize with |
|---|---|---|
| Blank OWL render | `t-name` mismatch JS<->QWeb; component not registered; error in `setup` | console `Missing template`/error; `module_inspect(name='<module>', method='owl', odoo_version='<version>')`, `find_examples` |
| Widget not showing | registry category/key wrong; field widget not registered | `take_snapshot` (node absent?); `module_inspect(name='<module>', method='js', odoo_version='<version>')`, `suggest_pattern` |
| RPC/action silently does nothing | failing RPC (4xx/5xx) swallowed; wrong model/method | browser network list; `find_override_point` server-side |
| SCSS override not applying | import order - winning definition loads after the override; wrong selector | `find_style_override`, `resolve_stylesheet` |
| Flat / off-theme render | token resolves EMPTY or self-referential `--bs-*` cycle (Odoo sets `$variable-prefix:''`) | `getComputedStyle(:root)`; see `odoo-frontend-fidelity.md` token-reality check |
| JS error after upgrade | core API symbol changed/removed | console stack; `lookup_core_api`, `api_version_diff` |

> Known gap: OSM has `find_override_point` for Python but no dedicated JS/OWL override-point tool.
> Infer JS/OWL location from `module_inspect(name='<module>', method='js', odoo_version='<version>')` (also try `method='owl'`) + `find_examples` +
> `suggest_pattern`, and state the inference explicitly rather than over-claiming certainty.

## Layer: Security / Access

| Symptom | Likely root cause | Localize with |
|---|---|---|
| `AccessError` on read/write | distinguish `ir.model.access` (CRUD per model/group) vs `ir.rule` (record-rule domain) | `model_inspect`; reproduce as the failing group; toggle with `sudo()` to confirm it is access (diagnose only, never fix-by-sudo) |
| Unexpected data visible/hidden | record rule domain too broad/narrow; missing company rule | inspect the rule's domain; `validate_domain` |
| Deep-dive for vulnerabilities (injection, XSS in QWeb, unsafe eval) | hand to `odoo-security-audit` (reactive mode) | - |

## Layer: Performance

| Symptom | Likely root cause | Localize with |
|---|---|---|
| List view / report very slow | N+1 ORM in a loop; non-stored computed used in list; missing prefetch | `resolve_orm_chain`; hand to `odoo-perf-audit` (reactive mode) for the full pass |
| Single query slow | unindexed field in domain/order; heavy `search` then filter in Python | `model_inspect` (field index); `validate_domain` |

## Layer: Install / Upgrade / Migration

| Symptom | Likely root cause | Localize with |
|---|---|---|
| Module won't install/load | unmet/wrong `depends`; failing data file; Python import error | `module_inspect` (manifest + depends); traceback bottom line |
| Migration script errors | wrong version path; pre/post hook assumptions; renamed model/field | grep `migrations/`; `api_version_diff` |
| Deprecated-API-at-runtime after upgrade | symbol removed/changed across versions | `lookup_core_api`, `api_version_diff`; for a full pre-upgrade scan hand to `odoo-deprecation-audit` |
