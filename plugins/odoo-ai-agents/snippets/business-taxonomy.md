# Business Taxonomy

A unit of work (a node, a module bundle, a requirement cluster, a module) carries ONE Domain line.
It is derived from data, written once, and read by every later step; no agent re-classifies it.

```
Domain: <business_function>; Audience: <role, role | n/a>; Outcome: <the business result the unit delivers>
```

## `business_function`

A closed set that does not change with the Odoo series: the table, plus `tax` and
`legal-compliance` by the signals of § Specialist list. Derive it from the module's own data
(`__manifest__.py` on disk for a module of the worktree set, `describe_module` otherwise); the
first rule that answers wins:

1. **Name**: `l10n_*` is `localization`; `hr_payroll*` is `payroll`.
2. **`category`**, read by meaning, never matched as a string: a segment that names
   localization, anywhere, decides `localization`; otherwise go from the LAST segment back to
   the first and take the first one that names a function of the table or something its Covers
   column lists. A segment that names none (a grouping word, an acronym you cannot expand) is
   skipped.
3. **What it builds on**: classify its `depends` by rules 1-2, then theirs, level by
   level; the first level that gives a function other than `productivity` and `platform`
   decides, and those two answer only when no level does. Two functions at one level: the
   one its `name` and `summary` speak of, else rule 4.
4. Nothing answers: `UNKNOWN`, never `platform`; the main agent decides and says from what.

| `business_function` | Covers | Default audience |
|---|---|---|
| `accounting` | invoicing, payments, bank, assets, analytic | accountant, chief accountant |
| `localization` | one country's chart, taxes, reports, e-invoicing | accountant of that country |
| `payroll` | payslips, salary rules | payroll officer, accountant |
| `sales` | quotations, orders, CRM, subscriptions | salesperson, sales manager |
| `point-of-sale` | shop and restaurant counters | cashier, shop manager |
| `inventory` | warehouse, stock, delivery, shipping | warehouse operator, inventory manager |
| `purchase` | requests for quotation, purchase orders | purchaser, purchase manager |
| `manufacturing` | production, quality, maintenance, repair | production planner, shop-floor operator |
| `human-resources` | employees, recruitment, time off, attendance, expenses, fleet | HR officer, employee, manager |
| `project-services` | projects, timesheets, field service | project manager, consultant |
| `helpdesk` | tickets, support | support agent, support manager |
| `website` | pages, eCommerce, eLearning, live chat | website visitor, web editor, shop manager |
| `marketing` | campaigns, events, surveys, social | marketer |
| `productivity` | discuss, calendar, documents, dashboards | every user |
| `platform` | hidden, technical, administration, tools, themes, tests | administrator, maintainer |

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

A request that spans functions gets one Domain line PER UNIT, never one for the request.
An interaction between two functions is its own line in the SRS or design, in the form
`A -> B: <business result>`; the function where the result lands owns the line, a specialist
function on either side first.

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
