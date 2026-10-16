<!-- SSOT snippet. The business-function taxonomy, the specialist list the model-tier rules read,
     and the Domain line every unit of work carries. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/business-taxonomy.md. -->

# Business Taxonomy

A unit of work (a node, a module bundle, a requirement cluster, a module) carries ONE Domain line.
It is derived from data, written once, and read by every later step; no agent re-classifies it.

```
Domain: <business_function>; Audience: <role, role | n/a>; Outcome: <the business result the unit delivers>
```

## `business_function` from the manifest `category`

Read `category` from the module's `__manifest__.py` (on disk for a module in the worktree set,
`describe_module` otherwise) and map its FIRST path segment; a second segment refines it. A value
not in the table is `UNKNOWN`; the main agent decides and the taxonomy gains a row.

| `category` (first segment / refinement) | `business_function` | Default audience |
|---|---|---|
| `Accounting` | `accounting` | accountant, chief accountant |
| `Accounting/Localizations/...`, any module named `l10n_*` | `localization` | accountant of that country |
| `Sales`, `Sales/Sales`, `Sales/CRM` | `sales` | salesperson, sales manager |
| `Sales/Point of Sale` | `point-of-sale` | cashier, shop manager |
| `Inventory/Inventory` | `inventory` | warehouse operator, inventory manager |
| `Inventory/Purchase` | `purchase` | purchaser, purchase manager |
| `Manufacturing` | `manufacturing` | production planner, shop-floor operator |
| `Human Resources` (any refinement except Payroll) | `human-resources` | HR officer, employee, manager |
| `Human Resources/Payroll`, any module named `hr_payroll*` | `payroll` | payroll officer, accountant |
| `Services/Project`, `Services/Timesheets`, `Services/Field Service` | `project-services` | project manager, consultant |
| `Services/Helpdesk` | `helpdesk` | support agent, support manager |
| `Website`, `Website/eCommerce` | `website` | website visitor, web editor, shop manager |
| `Marketing` | `marketing` | marketer |
| `Productivity`, `Discuss` | `productivity` | every user |
| `Hidden`, `Technical`, `Administration`, `Theme` | `platform` | administrator, maintainer |

A module whose manifest has no `category` is `UNKNOWN`, never `platform`.

## Specialist list (the model-tier rules read it)

A unit is specialist when its `business_function` is one of: `accounting`, `localization`,
`payroll`, `tax` (a module whose name contains `tax` or whose SRS names a tax rule), or
`legal-compliance` (the SRS names a statute, a regulation, a statutory report or an e-invoicing
mandate). A specialist unit takes the opus rows of
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Model-tier selection; nothing else
in the same run inherits that tier.

## Where the line is written

| Unit | Written by | From |
|---|---|---|
| A node of a feature | the architect in the SRS, copied by the planner into the node | the SRS scope and the manifests of the modules the node touches |
| A module bundle of a forward-port, backport, rebase or upgrade | the intent extractor or the recon agent | the bundle's manifests and the commit intents |
| A requirement cluster (BRL, gap analysis) | the cluster's analyzer | the requirement text and the modules it maps to |
| A module (i18n, doc, audit) | the main agent | the module's manifest |
| An incident | the debug agent | the manifest of the module that owns the root cause |

## Several functions in one request

A request that spans functions (a forward-port of a whole branch, "confirm the order and post the
invoice", an ERP-wide requirement list) gets one Domain line PER UNIT, never one for the request.
An interaction between two functions is its own line in the SRS or design, in the form
`A -> B: <business result>` (`sales -> accounting: revenue is recognized on confirmation`); the
function where the result lands owns the line, and when `accounting`, `payroll`, `tax`,
`localization` or `legal-compliance` is on either side, it owns the line.

## `Audience: n/a`

A unit no end user operates (a pure refactor, a technical bridge, a lint fix) writes `n/a`
explicitly; the audience gate in review and documentation then does not apply. An empty audience
is a defect, not a default.

## The audience gate (review `R2`, documentation)

Three closed questions, answered against the Domain line's roles:
1. Does each role named find the feature where that role works (menu, view, report, action)?
2. Does each role understand every label, message, empty state and error the change shows, without
   reading code or a manual?
3. Can each role tell, from what the screen shows, what the change did for them?
A "no" is a finding with the role and the screen named.
