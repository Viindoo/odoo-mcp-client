# odoo-customer-health - Worked Examples

## Example 1 - Amber account, idle license syndrome

**Context provided by user:**
- Customer: Customer A - wholesale distribution, 45 employees
- Go-live: 14 months ago (Inventory, Purchase, Accounting, Sales)
- Login frequency: "maybe 2-3 people log in daily, others rarely"
- Open tickets: 2, both < 7 days old
- Last CSM call: 3 months ago
- No executive sponsor change, no competitor signals

**Output (excerpt):**

```
# Customer Health Report - Customer A

## Health Score
**AMBER** - Low adoption breadth and a 3-month touchpoint gap create renewal risk.

Score basis: 4 / churn signals: 2 / data-poverty penalty: not applied

## Churn Signals
1. Login frequency sporadic: only 2-3 of 45 users log in daily -> majority of named users
   are not extracting value; customer may not justify renewal cost at review time.
2. Last CSM touchpoint > 60 days ago: 3 months since last call -> no recent visibility into
   satisfaction, no relationship maintenance.

## Adoption Snapshot
- Modules actively used: Inventory, Sales, Accounting (partial)
- Modules licensed but idle: Purchase (used by procurement lead only)
- Login frequency: sporadic (2-3 / 45 daily)
- Open tickets: 2, oldest 6 days
- Last CSM touchpoint: ~90 days ago

## Upsell / Expansion Opportunities
1. Helpdesk module: distributor with 45 staff likely manages customer complaints ad-hoc;
   Helpdesk centralizes this and creates a visible win for the team - Effort: Low
2. Purchase adoption deepening (config, not upsell): Purchase is licensed but barely used;
   an adoption workshop could unlock visible ROI from an already-paid license - Effort: Low
   [no new revenue but prevents churn by surfacing value]

## Recommended Next-Touch Action
**Owner:** CSM
**Action:** Schedule a 45-minute adoption workshop focused on Purchase module and daily
reporting habits; invite the operational manager (not just the Odoo admin).
**Deadline:** Within 2 weeks
```

---

## Example 2 - Red account, champion lost + renewal imminent

**Context provided by user:**
- Customer: Customer B - professional services firm, 80 employees
- Go-live: 22 months ago (CRM, Project, Timesheets, Invoicing)
- Their internal Odoo admin resigned 6 weeks ago; no replacement named yet
- 9 open tickets, oldest 45 days unresolved
- Renewal in 38 days
- No recent CSM contact

**Output (excerpt):**

```
# Customer Health Report - Customer B

## Health Score
**RED** - Champion loss, unresolved ticket backlog, and an imminent renewal without a
live CSM relationship is a high-probability churn scenario.

Score basis: 10 / churn signals: 4 / data-poverty penalty: not applied

## Churn Signals
1. Champion lost (internal admin resigned, no replacement): highest-severity signal -> no
   internal advocate to justify renewal; decision-maker now has no emotional attachment to
   the platform.
2. >5 open tickets, oldest 45 days: visible pain with no resolution signal -> user
   frustration is compounding; this is the most likely surface-level complaint at renewal.
3. Renewal < 60 days and no conversation started: 38 days is inside the danger zone ->
   without a live renewal conversation, the default action for a frustrated customer is
   non-renewal.
4. Last CSM touchpoint unknown / no recent contact: no relationship visibility -> CSM
   cannot assess the real internal temperature.

## Recommended Next-Touch Action
**Owner:** AM + CSM + CEO
**Action:** Joint escalation call with customer's department head or CFO within 5 business
days. Agenda: (1) acknowledge the support backlog and commit to a resolution sprint, (2)
offer a complimentary admin handover session to onboard a new internal champion, (3) frame
the renewal as a partnership investment, not a transaction.
**Deadline:** Within 5 business days
```
