---
name: odoo-security-audit
description: >
  Audit Odoo Python, JavaScript, XML, and QWeb code for security vulnerabilities - severity-graded
  findings report with file/line, exploit path, and concrete fix. Reporting only - does NOT write
  fixes. Covers: SQL injection (cr.execute with f-string/% concat), XSS (t-raw / Markup misuse),
  access control gaps (missing ir.model.access.csv, sudo() ACL bypass, unsafe auth='public'),
  CSRF, unsafe deserialization (eval/pickle/safe_eval), hardcoded secrets. Trigger on: "audit
  security", "is this code safe", "SQL injection risk", "XSS in QWeb", "check access control",
  "sudo bypass", "hardcoded secret", "CSRF in controller". Vietnamese triggers: "kiểm tra bảo
  mật code Odoo", "có bị SQL injection không", "review bảo mật trước khi deploy", "t-raw có an
  toàn không". Also fires when user shares controller/model/view code and asks "okay to ship?" or
  "anything to worry about". For fixes route to odoo-coding; for
  a runtime symptom needing root-cause route to odoo-debug
model: inherit
---

## Persona

Security-focused Developer / Tech Lead auditing Odoo source code with OSM-grounded analysis.

## Out of Scope

- **Writing fixes** - route to `odoo-coding`
- **Pre-upgrade deprecation sweep** - route to `odoo-deprecation-audit`
- **Live render or runtime error verification** - route to `odoo-debug`
- **Performance / N+1 / convention review** - route to `odoo-code-review`
- **Override safety** - route to `odoo-override-finding`

## When to use

Invoke this skill whenever:
- Code is shared (pasted, file path referenced, or available from a prior step) and security, safety, or deployment readiness is the concern
- A PR touches controllers, model methods with `sudo()`, QWeb templates with `t-raw`, or CSV access files
- A module is being deployed or reviewed for the first time and no prior security audit exists

**Reactive mode (dispatched by `odoo-debug`).** When `odoo-debug` routes a runtime security
symptom here (an observed leak, an unexpected `AccessError`, an apparent injection - with a
reproduction + version), root-cause THAT symptom following the scientific method
(`${CLAUDE_PLUGIN_ROOT}/skills/_shared/debug-method.md`) and emit the same graded report. A direct
invocation with no specific symptom stays a proactive vulnerability audit.

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
_Tool surface: server v0.13.1. See [`docs/reference/mcp-tool-routing.md`](../../docs/reference/mcp-tool-routing.md) for full routing matrix._

> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Primary tools:**
- `model_inspect` ★ — Superset inspection of an ORM model: enumerate or fully describe fields, methods, views, extenders, or a summary in one call.
- `find_examples` — Semantic code search returning real indexed code snippets from the Odoo codebase.
- `lookup_core_api` — Verify Odoo core API symbol signature, status (stable/deprecated/removed), and replacement.
- `lint_check` — Validate code against Odoo-specific lint rules (Python/JavaScript), or return corpus-level XML RelaxNG violation nodes (language='xml', server v0.9.1+).
- `entity_lookup` ★ — Single-entity drill-down by ID: field, method, or view with full inheritance chain and source module.
<!-- END GENERATED TOOLS -->

## Method

Use parallel MCP calls to minimize round trips. A full audit completes in 3-4 rounds.

### Round 0 - Pin version + profile

`set_active_version(odoo_version=<target>)` then `set_active_profile(profile_name=<profile>)`.
Resolve target version from `.odoo-ai/context.md`; if absent, derive from manifest `version` fields.

### Round 1 - Parallel triage (all independent, fire together)

1. `lint_check` on the Python/JS source as a quick first pass - note results are hints, not gates.
2. `find_examples(query='safe_eval usage', odoo_version='auto')` - retrieve indexed safe_eval examples to compare against audited code.
3. `find_examples(query='http.route auth public', odoo_version='auto')` - retrieve controller auth patterns.
4. `find_examples(query='t-raw QWeb XSS Markup', odoo_version='auto')` - retrieve safe QWeb output patterns.

### Round 2 - Pattern scan + model/method inspection (parallel)

Fire all independent scans simultaneously:
- `model_inspect` on each model in scope (`method='methods'`) to enumerate methods and flag sudo() usage counts.
- `entity_lookup(kind='method', ...)` for each method identified as suspicious in Round 1 (sudo() call, cr.execute, t-raw).
- `lookup_core_api(name='safe_eval', odoo_version='auto')` to verify the exact safe API signature.
- `lookup_core_api(name='Markup', odoo_version='auto')` to confirm correct Markup/escape usage.
- `lookup_core_api(name='http.route', odoo_version='auto')` for the auth parameter's accepted values.

### Round 3 - Access control verification (parallel)

- `find_examples(query='ir.model.access model access csv', odoo_version='auto')` - verify expected CSV structure.
- `find_examples(query='ir.rule record rule domain', odoo_version='auto')` - baseline record rule patterns.
- Cross-reference with local file scan (see Standalone-first fallback Tier 2) if OSM results are inconclusive.

**Disk scan supplement** (always run alongside OSM rounds, not instead of):

```bash
# SQL injection candidates
grep -rn "cr\.execute\|self\._cr\.execute" --include="*.py" . | grep -v "%s\|param"

# XSS candidates
grep -rn "t-raw\|t-esc=" --include="*.xml" .
grep -rn "innerHTML\|Markup(" --include="*.js" .

# sudo() usage
grep -rn "\.sudo()" --include="*.py" .

# eval / pickle / unsafe deserialization
grep -rn "\beval(\|pickle\.\|safe_eval(" --include="*.py" .

# Hardcoded secrets
grep -rn "password\s*=\s*['\"].\|api_key\s*=\s*['\"].\|secret\s*=\s*['\"]." --include="*.py" .

# Public routes
grep -rn "auth='public'\|auth=\"public\"" --include="*.py" .

# Missing access CSV
find . -maxdepth 4 -name "__manifest__.py" | xargs grep -l "security" | \
  xargs -I{} dirname {} | xargs -I{} sh -c 'ls {}/security/ir.model.access.csv 2>/dev/null || echo "MISSING: {}/security/ir.model.access.csv"'
```

Each hit becomes a candidate finding; OSM rounds confirm exploitability and suggest the canonical safe pattern.

## Security issue taxonomy

### SQL injection

**Vulnerable patterns:**
```python
# CRITICAL - f-string interpolation
self.env.cr.execute(f"SELECT id FROM res_partner WHERE name = '{name}'")

# CRITICAL - % string formatting
self.env.cr.execute("SELECT id FROM res_partner WHERE name = '%s'" % name)

# CRITICAL - + concatenation
self.env.cr.execute("SELECT * FROM " + table_name + " WHERE id = %d" % id)
```

**Safe pattern** (parameterized, always):
```python
self.env.cr.execute("SELECT id FROM res_partner WHERE name = %s", (name,))
```

**Exploitability note:** Any unsanitized user-controlled string reaching `cr.execute` allows arbitrary SQL on the PostgreSQL session. Odoo runs on a single DB user - a successful injection can read any table including `res.users` password hashes.

### XSS - QWeb / t-raw

**Vulnerable patterns:**
```xml
<!-- CRITICAL if content is user-controlled -->
<span t-raw="record.description"/>

<!-- HIGH - innerHTML assignment in JS/OWL without sanitization -->
```

**Safe patterns:**
```xml
<!-- Use t-esc for all user-supplied text -->
<span t-esc="record.description"/>

<!-- Use t-out (v16+) for trusted HTML that was explicitly sanitized -->
<span t-out="record.html_field"/>
```

**Markup misuse:** `Markup(user_input)` marks a string as safe WITHOUT sanitizing it - only use `Markup` on strings you have already sanitized with `html.escape()` or that come from a trusted source (e.g. `fields.Html` with `sanitize=True`).

### Access control gaps

| Gap | Severity | Detection |
|-----|----------|-----------|
| Model has no `ir.model.access.csv` entry | HIGH | file scan |
| `sudo()` without narrowing env | HIGH | grep + entity_lookup |
| `@http.route(auth='public')` exposing write methods | CRITICAL | grep + lookup_core_api |
| No record rules on multi-company model | MEDIUM | model_inspect + find_examples |
| `groups=` attribute absent on sensitive menu/button | MEDIUM | XML scan |

**sudo() safe vs. unsafe:**
```python
# UNSAFE - broad bypass, any caller gets full admin rights
record = self.env['res.partner'].sudo().search([])

# SAFER - scoped: immediately drop privileges after single operation
sudo_env = self.env(su=True)
partner = sudo_env['res.partner'].browse(partner_id)
# re-scope immediately; do not pass sudo_env further
```

### CSRF

Odoo has built-in CSRF protection for `POST` requests via the session token. Gaps arise when:
- A controller uses `csrf=False` explicitly without compensating controls.
- A `GET` route performs state-changing operations (violates HTTP semantics and bypasses CSRF token check).

```python
# HIGH - CSRF disabled with no compensating control
@http.route('/my/endpoint', auth='user', methods=['POST'], csrf=False)
```

### Unsafe deserialization

```python
# CRITICAL - arbitrary code execution
eval(user_input)
pickle.loads(user_data)

# HIGH - safe_eval is safer but still dangerous with untrusted input
from odoo.tools.safe_eval import safe_eval
safe_eval(user_expression, {})  # user_expression must NOT come from HTTP request body unvalidated
```

**OSM ground truth:** call `lookup_core_api(name='safe_eval', odoo_version='auto')` to confirm the exact allowed locals/globals API for the target version before flagging a finding.

### Hardcoded secrets

```python
# CRITICAL
API_KEY = "sk-proj-xxxxx"
password = "admin123"
```

Any credential, token, or secret literal in committed Python/XML/JS/config is CRITICAL regardless of the deployment context.

## Output format

```
## Security Audit Report

**Scope:** <files / module / PR description>
**Odoo version:** <version>
**Grounding:** <osm / local-source / OSM unavailable - ungrounded>
**Files scanned:** <N>
**Issues found:** <N total> (<N> CRITICAL / <N> HIGH / <N> MEDIUM / <N> LOW)

### Findings

| # | Severity | Category | File | Line | Summary |
|---|----------|----------|------|------|---------|
| 1 | CRITICAL  | SQL injection | `models/sale.py` | 42 | f-string in cr.execute |
| 2 | HIGH      | XSS | `views/templates.xml` | 88 | t-raw on user-controlled field |
| ... | ... | ... | ... | ... | ... |

---

#### Finding 1 - CRITICAL: SQL injection in `SaleOrder._compute_total`

**File:** `models/sale.py:42`
**Vulnerable code:**
```python
self.env.cr.execute(f"SELECT SUM(price_unit) FROM sale_order_line WHERE order_id = {self.id}")
```
**Why exploitable:** `self.id` is attacker-controlled in multi-company contexts where record IDs
can be enumerated. Even with integer coercion, the pattern is a bad practice that will break
type-checking and opens injection risk if the variable type widens in a future refactor.
**Concrete fix:**
```python
self.env.cr.execute(
    "SELECT SUM(price_unit) FROM sale_order_line WHERE order_id = %s",
    (self.id,)
)
```

---

#### Finding 2 - HIGH: XSS via t-raw on user-controlled field

... (same structure per finding)

---

### Risk summary

<2-4 sentences on overall security posture, highest-priority issues, and recommended first actions>

### Recommended remediation order

1. Fix all CRITICAL issues before any public deployment
2. HIGH issues: fix in current sprint
3. MEDIUM: schedule in next sprint
4. LOW: address in follow-up cleanup
```

## Standalone-first fallback

When OSM is unreachable, follow the three-tier grounding in
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md`:

- **Tier 2 - Disk scan:** Run the grep commands from the Method section above against the local
  source tree. This surfaces all SQL injection candidates, XSS candidates, sudo() calls, eval/
  pickle, public routes, and hardcoded secrets directly from source without MCP.
- **Tier 2 - Access CSV check:** Run the `find` command to detect models missing `ir.model.access.csv`.
- **Tier 2 - Version:** Read `.odoo-ai/context.md` for `odoo_version`; derive from manifest if absent.
- **Caveat:** Label output `grounded: local-source (not OSM-indexed)`. OSM-enriched exploitability
  context (inheritance chain, exact API signature for `safe_eval`/`Markup`) is unavailable - note
  findings as "requires OSM verification for full exploit path". Classification is based on static
  pattern matching.
- Escalate to caller (`NEEDS_CONTEXT`) only if the target version is genuinely unresolvable and
  severity grading would materially change between versions - never ask the caller to supply code
  or file lists that a disk scan can retrieve.

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the depth-0 run-driver - it does not change anything produced above.
