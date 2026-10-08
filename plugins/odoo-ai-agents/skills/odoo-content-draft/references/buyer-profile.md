# Buyer profile - template

The `## Buyer profile` block Round 0.5 returns. It names who buys the module, in which segment,
what hurts them today and what outcome they buy, so every section of the copy answers a pain or a
messaging pillar below. This skill writes no file: the caller saves the block as `buyer-profile.md`
next to the module's `feature-catalog.jsonl`.

## Target market

`TARGET MARKET` is the market the copy addresses: a region or localization, plus the vertical when
the module has one. When neither the brief nor the request carries it, propose a value from the
module descriptor and have the user confirm it before use:

- an `l10n_<cc>` module name, or an `l10n_<cc>` entry in `depends` -> the country `<cc>` names;
- a `countries` key -> those countries;
- `category` -> the vertical;
- none of these -> `region-neutral` (the copy names no country).

A value the user has not confirmed and the brief does not carry is never used.

## Rules

- Ground every row in a fact from the inputs: the feature catalog (`feature_id`, `name`, `value`),
  the role map (`roles[]` with `business_role` and `job`, `process[]`), the module descriptor
  (`summary`, `category`, `depends`, the module name) and `TARGET MARKET`. A row no fact supports is
  left out or carries `<TBD>`.
- No invented numbers, customer names, quotes or testimonials.
- The region comes only from `TARGET MARKET`.
- State only what the module supports: never mention an edition it does not run on, never compare
  it with another product's equivalent feature, and never name a competing product. "Best for" says
  who the module fits; there is no row for who it does not fit.

## Block

```markdown
## Buyer profile - <module display name>

target_market: <TARGET MARKET value>   (source: brief | confirmed-at-gate)
inputs: <feature-catalog.jsonl path>, <role-map.json path | none>, <module descriptor path>

### Segments
| Axis | Segment | Supporting module fact |
|---|---|---|
| Industry / vertical | <segment> | <manifest `category`, catalog features> |
| Company size | <segment> | <role map: how many roles and handoffs the process needs; `depends`> |
| Region / localization | <from TARGET MARKET> | <`l10n_<cc>` name or depends, `countries` key, or region-neutral> |

### Buying committee
| Member | Who | Pains | Desired outcomes | What convinces |
|---|---|---|---|---|
| Economic buyer | <who signs off the purchase> | | | |
| Champion | <who runs the process day to day and pushes for the module> | | | |
| End users | <each role-map `business_role`, one row each or grouped> | | | |
| Technical evaluator | <who installs and maintains it> | | | <`depends`, license, setup effort> |

### Status quo
<2-4 bullets: how the committee does this work today without the module - spreadsheets, email
threads, manual re-entry, paper approvals. Never name a competing product.>

### Top objections
| Objection | Answer | Proof (`feature_id` or `<TBD>`) |
|---|---|---|

### Best for
<One or two sentences naming the segment the module fits best.>

### Messaging pillars
| Pillar | Pain it answers | Proof (`feature_id` or process stage) |
|---|---|---|
```
