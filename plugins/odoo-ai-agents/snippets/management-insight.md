# Management insight (reports and dashboards)

The owner of a business and the managers of a function use the software to see and to decide. A
change that creates or changes business data is designed and built together with what they will
read from it: a new report or dashboard, or an existing one adjusted or extended.

## At design - the SRS section `## Management insight`

Per management role of the SRS Domain line: the questions the role answers and the decisions it
takes on the data this change creates or changes (amounts, quantities, durations, dates, states,
parties), predicted from the role's job, not from the request's wording. Each question gets one
proposal, the first that holds:

1. **covered** - a report, dashboard or analysis view of the standard product or of the module
   already answers it: named, with its source row;
2. **adjust** - an existing one gains a measure, a dimension, a filter, a grouping or a default;
3. **extend** - an existing report model or dashboard gains the new data;
4. **new** - a report, a dashboard, or a printed document a manager signs or files.

The mechanism is the one the series' core uses for that kind of report, confirmed in the index
before it is named. A figure the data cannot produce is not proposed. Every proposal is marked
`in scope` or `proposed` and the human settles it at the SRS gate: an in-scope one carries an
acceptance criterion (the figure the report shows for stated records, computed by hand) and demo
data that gives it a shape - several periods, several values of each dimension. A change with no
business data writes `none - <reason>`.

## At build

A coder makes the data its node adds reachable where the managers already look - the measure,
dimension, filter or grouping of an existing report of the same modules - and may add a small
report the outcome clearly needs, inside its `MODULES`, with tests; it lists each addition and
its reason in its return. Anything larger, or in a module outside the node, is returned as a
proposal. The launcher keeps an addition that is sound and serves the outcome, and passes the
proposals to the human.

## In the docs

The feature catalog marks such a capability `type: report` with the question it answers
(`${CLAUDE_PLUGIN_ROOT}/skills/odoo-doc-illustration/references/doc-artifacts.md`); the guide
and the store page's INSIGHTS section read it from there.
