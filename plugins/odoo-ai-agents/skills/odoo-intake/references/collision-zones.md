# Intake - Collision Zones (worked examples)

Load this when two candidate skills overlap and the Routing Table's **Discriminator** column
is not enough to break the tie - the canonical resolution logics for known collision zones. The
one-line discriminators already live in the Routing Table; this file elaborates with worked
prompts and "if the user had said X instead" counter-cases.

## Collision 1 - Objection vs Capability Proof

**Prompt**: "write a response to the customer saying Odoo doesn't support multi-level approval"

- `odoo-objection-handling`: handles "respond to objection", "customer says Odoo
  can't" -> produces a verbatim ACA-framework response paragraph.
- `odoo-capability-proof`: handles "Odoo doesn't support X" -> produces a
  technical evidence package (modules + code snippets + demo steps).

**Discriminator**: the verb "write a response" signals the user wants a customer-facing
paragraph they can paste. -> **Pick `odoo-objection-handling`.**

Had the user said "prepare technical evidence for the multi-level approval demo" ->
`odoo-capability-proof`.

## Collision 2 - Version Diff vs Feature Highlights

**Prompt**: "summarize the key highlights in Odoo 18 for an internal slide next week"

- `odoo-version-diff`: handles "new features in Odoo X" -> produces dev-track
  diff + marketer-track summary.
- `odoo-feature-highlights`: handles "feature highlights", "slide", "for the
  newsletter" -> produces business-language highlights with optional dev appendix.

**Discriminator**: "internal slide" + "summarize" signal marketing/non-developer output.
-> **Pick `odoo-feature-highlights`.**

Had the user said "which APIs changed from v17 to v18, dev team needs to know" ->
`odoo-version-diff`.

## Collision 3 - Deprecation Audit vs Version Diff

**Prompt**: "customer is asking what's different between v16 and v17"

- `odoo-deprecation-audit`: handles "what will break", "audit before upgrade" ->
  scans the user's codebase for deprecated API usage.
- `odoo-version-diff`: handles "what changed between two versions", "version-to-version diff"
  -> pure API/feature diff without scanning user code.

**Discriminator**: "customer is asking" + no mention of "our code" or "audit" signals the user
wants a clean diff to relay, not a code scan. -> **Pick `odoo-version-diff`.**

Had the user said "audit the customer's codebase before upgrading to v17" ->
`odoo-deprecation-audit`.

## Collision 4 - Deal Follow-up vs Objection Handler

**Prompt**: "customer hasn't replied in a while, need to write a follow-up"

- `odoo-deal-followup`: handles "customer hasn't replied", "draft follow-up email"
  -> sales AE re-engagement email (cold/warm/engagement).
- `odoo-objection-handling`: handles "write a response", "respond to objection" ->
  counter-response to a stated objection.

**Discriminator**: "hasn't replied" (silence) + "follow-up" signal the user wants a
re-engagement email, not a counter to an objection. -> **Pick `odoo-deal-followup`.**

Had the user said "customer says Odoo doesn't support X, I need to write a response" ->
`odoo-objection-handling`.

## Collision 5 - Skill vs Command (same domain)

**Prompt**: "synthesize these discovery notes for the Acme deal"

- `odoo-discovery-summary` (SKILL, row 16): handles "synthesize discovery
  notes", "extract customer profile" -> produces structured profile.
- `/odoo-summarize-discovery` (COMMAND, row 25): same purpose but is the slash-command wrapper.

**Discriminator**: no slash prefix in user prompt + intent is single-step (just synthesize,
not save) -> **Pick SKILL `odoo-discovery-summary`**.

If the user had typed "/odoo-summarize-discovery" -> command invokes directly (intake not
consulted). If user said "synthesize discovery + save to .odoo-ai/" -> recommend the COMMAND
for the save step.

## Collision 6 - Capability Proof (text evidence) vs Demo Recorder (real video)

**Prompt**: "I need a demo of multi-currency invoicing for the prospect this Friday"

- `odoo-capability-proof`: handles "demo material", "for the demo, give me proof"
  -> produces a TEXT evidence package (module names + code snippets + written demo steps).
- `odoo-demo-recording`: handles "record a demo", "make a video walkthrough"
  -> drives the live instance and produces a REAL MP4/GIF screencast.

**Discriminator**: "demo" alone is ambiguous. If the deliverable is written proof / RFP
evidence the rep can paste, -> **Pick `odoo-capability-proof`**. If the user wants an actual
recorded video/clip of the flow running on a live instance ("record", "video", "screencast",
"GIF"), -> **Pick `odoo-demo-recording`**. When unclear, ask: "written evidence package, or a
recorded video of the flow?"

## Collision 7 - Coding (write JS) vs UI Debug (debug runtime)

**Prompt**: "my OWL widget isn't showing up in the Odoo 17 form"

- `odoo-coding`: handles "field widget customization Odoo 17", "patch
  component" -> WRITES new/changed frontend JS source (its frontend leg).
- `odoo-debug`: handles "widget không hiện", "OWL component not rendering" ->
  investigates the live runtime to find the ROOT CAUSE of the missing render.

**Discriminator**: a symptom + "why / not showing / isn't working" signals the user needs the
cause first, not new code. -> **Pick `odoo-debug`**. Once the cause is known and the user
asks for the fix to be written, -> route to `odoo-coding`. If the user is starting
from scratch ("create a color picker widget"), there is no runtime to debug ->
`odoo-coding`.

## Collision 8 - BRL Scale vs Ad-hoc Gap Analysis vs Single Feature

**Discriminator**:
- **1 feature** → `odoo-feature-check`
- **Short ad-hoc list (< ~20 items), no cost/DAG/RTM requirement** → `odoo-gap-analysis`
- **Hundreds to thousands of items, OR explicit cost estimate, OR dependency graph / RTM output requested** → `odoo-brl`

**Prompt examples**:
- "Does Odoo support multi-currency invoicing?" → `odoo-feature-check` (single feature)
- "Customer needs A, B, C - which does Odoo have, estimate effort" → `odoo-gap-analysis` (short list, ad-hoc)
- "We have 1200 requirements from the RFP - classify, cost, and produce a dependency graph" → `odoo-brl` (scale + cost + DAG)
- "50 requirements but we also need the RTM and cost table" → `odoo-brl` (explicit RTM + cost signals override small count)
- "Classify these requirements" (no count stated) → ask: "How many requirements? If tens or more with cost/traceability needs, odoo-brl; short ad-hoc list → gap-analysis."

## Collision 9 - Parallel multi-WI delivery (odoo-planning) vs BRL (requirement classification) vs Coding (single change)

**Prompt**: "I have 5 changes to make across 3 files - parallelize them and land as a single reviewed PR"

- `odoo-planning`: handles the USER-facing "parallelize these changes", "multi-WI PR with review +
  squash" intent -> it produces the wave-batched EXECUTION PLAN. The git orchestration itself
  (integration branch, parallel WI worktrees, cherry-pick, end-of-wave review, 1 PR, squash, then
  STOP at the L2-squash-gate) is the INTERNAL `odoo-wave` executor, which `run-harness` dispatches
  from the approved plan; `odoo-wave` never merges - the merge is owned by the subsequent
  `odoo-pr-monitoring` at the L2-merge-gate. `odoo-wave` is `user-invocable: false` - never route a
  user prompt to it.
- `odoo-brl`: handles "classify changes", "requirements" -> classifies and costs a
  list of BUSINESS REQUIREMENTS - produces an RTM/cost/DAG but writes NO code and does NOT touch git.
- `odoo-coding`: handles "implement feature", "write code" -> writes code for a SINGLE
  change (backend and/or frontend) in the current working directory; no git orchestration, no worktrees.

**Discriminator**:
- "parallelize" + "N changes" + "PR" + "squash" signal parallel multi-WI delivery ->
  **Pick `odoo-planning`** (it plans it; `run-harness` then drives the internal `odoo-wave` executor).
- "classify/cost requirements" or "RTM/DAG" with no code-generation intent -> **Pick `odoo-brl`.**
- Single change, single feature, no git coordination needed -> **Pick `odoo-coding`.**

If the user said "write a computed field for sale.order" -> `odoo-coding` (single, no orchestration).
If the user said "classify 200 requirements from the RFP" -> `odoo-brl` (no code, no git).
If the user said "we have a bug fix, a test addition, and a docs update - land them as one reviewed PR"
-> `odoo-planning` (multiple disjoint changes; it plans the wave-batched delivery for the internal
`odoo-wave` executor).

## Collision 10 - Doc Illustration (static screenshots) vs Demo Recording (real video)

**Prompt**: "tôi cần tài liệu cho module Sale với ảnh chụp màn hình minh hoạ các bước"

- `odoo-doc-illustration`: handles "viết tài liệu module / cập nhật tài liệu có ảnh chụp màn hình /
  làm static/description / document this module" -> produces a STATIC written guide with annotated
  screenshots captured from the live instance, saved as docs/description files.
- `odoo-demo-recording`: handles "quay video tính năng / demo video / screencast / GIF" ->
  drives the live instance and produces a REAL recorded MP4/GIF screencast of a flow.

**Discriminator**: "ảnh chụp" / "screenshot" / "tài liệu" / "docs" + no mention of "video",
"quay", "screencast", "GIF" -> **Pick `odoo-doc-illustration`**. If the user wants a playable
recording of the flow ("video", "quay lại", "GIF"), -> **Pick `odoo-demo-recording`**.
When the user says "demo" with no further qualifier, ask: "static screenshot doc, or recorded video?"

**Tie-breaker rule**: deliverable is a DOCUMENT (text + still images) -> `odoo-doc-illustration`;
deliverable is a PLAYABLE RECORDING (mp4/GIF) -> `odoo-demo-recording`.

## Collision 11 - Rebase vs Forward-Port vs Parallel multi-WI delivery

**Prompt**: "I need to rebase my feature branch onto the updated 17.0 base - there are about 12
commits to replay and a few conflicts to resolve."

- `odoo-git-rebase`: handles "rebase branch onto another branch SAME series" -> whole-range
  a rebase that replays the <upstream>..<branch> range onto <newbase> and resolves
  conflicts in-flight; SAME Odoo major throughout.
- `odoo-forward-port`: handles "port a commit/PR to a HIGHER major version" -> single-commit
  cherry-pick + adapt across a version boundary (e.g. 16.0 -> 17.0).
- `odoo-planning`: handles "parallelize N disjoint work items into one squashed PR" -> it produces
  the wave-batched plan; the cherry-pick + squash of N independent changes that do NOT share a
  continuous range is performed by the INTERNAL `odoo-wave` executor (dispatched by `run-harness`
  from the approved plan), not by the user. `odoo-wave` STOPS at the L2-squash-gate and never
  merges - the merge is owned by the subsequent `odoo-pr-monitoring` at the L2-merge-gate.

**Discriminator**: same Odoo series + one branch's whole commit range to replay ->
**Pick `odoo-git-rebase`**. Cross-major single commit/PR to port -> `odoo-forward-port`. Many
disjoint changes to land together -> **Pick `odoo-planning`** (it plans the delivery; the internal
`odoo-wave` executor performs the cherry-pick + squash and STOPS at the L2-squash-gate, the merge
owned by `odoo-pr-monitoring`).

If the user said "rebase my 17.0-custom onto origin/17.0" -> `odoo-git-rebase` (same series,
whole range).
If the user said "port this 16.0 fix to 17.0" -> `odoo-forward-port` (cross-major, single commit).
If the user said "land the bugfix, the new field, and the docs update as one reviewed PR" ->
`odoo-planning` (disjoint WIs, no range replay; planned for the internal `odoo-wave` executor).

## Collision 12 - Modules-Upgrade vs Forward-Port vs Plan-Upgrade vs Deprecation-Audit vs Version-Diff

**Prompt**: "nâng cấp cluster sale_custom + sale_discount từ Odoo 16 lên 17 - cần code chạy được
và xoá module nào core đã hấp thụ."

- `odoo-modules-upgrade`: EXECUTE a cross-major cluster upgrade at CODE level - adapts source so
  modules are installable and working on the target series, deletes core-absorbed modules, produces
  a mergeable PR.
- `odoo-plan-upgrade`: produces a PLAN / risk dashboard only - no code written, no files changed;
  for decision-makers who want scope and risk before committing to the upgrade.
- `odoo-forward-port`: moves ONE commit from one major to the next - not a full module adaptation,
  not a cluster upgrade.
- `odoo-deprecation-audit`: scans for deprecated-symbol usage only - detection report, no fixes.
- `odoo-version-diff`: reports API delta between two versions - what changed, added, removed - no
  code changes, no upgrade execution.

**Discriminator**: "execute + produce working code / PR" for a cluster across majors ->
**Pick `odoo-modules-upgrade`**. "just give me a plan / risk overview, no code" ->
`odoo-plan-upgrade`. "move one commit to the next major" -> `odoo-forward-port`. "scan for
deprecated symbols only" -> `odoo-deprecation-audit`. "show me what the API changed between
versions" -> `odoo-version-diff`.

If the user said "tell me what risks I face upgrading to v17 but don't touch the code yet" ->
`odoo-plan-upgrade` (plan only).
If the user said "make our modules actually run on v17" -> `odoo-modules-upgrade` (execute).

## Collision 13 - feature-check vs doc-feature-map vs feature-highlights

**Prompt**: "list all the features of the purchase module" or "what can this module do?"

- `odoo-feature-check`: answers ONE specific feature availability question with a yes/no verdict
  ready for a client email (e.g. "does purchase have landed costs?"). Single-feature, evidence-backed.
- `odoo-doc-feature-map`: produces a FULL enumeration of all capabilities a module ships for
  documentation purposes - iterates over every feature group, model, view type, and workflow.
- `odoo-feature-highlights`: marketing-framed "what's new in version X" summary - version delta
  with business audience framing, not a complete capability catalogue.

**Discriminator**: single yes/no availability question -> **`odoo-feature-check`**. Enumerate
ALL features for docs -> **`odoo-doc-feature-map`**. "What's new in Odoo 17 for this module" /
marketing framing -> `odoo-feature-highlights`.

If the user said "does purchase support multi-currency?" -> `odoo-feature-check` (one feature).
If the user said "list every feature purchase ships so I can write the module docs" ->
`odoo-doc-feature-map` (full inventory for documentation).
If the user said "what's improved in purchase in v17 for our release blog" ->
`odoo-feature-highlights` (version-delta marketing).

## Collision 14 - customization-inventory vs doc-feature-map

**Prompt**: "inventory what this module does" or "map all the capabilities of sale_custom".

- `odoo-customization-inventory`: executive summary of CUSTOM code in a CLIENT'S instance -
  what Viindoo (or the partner) has built on top of Odoo standard, for an engagement deliverable.
- `odoo-doc-feature-map`: enumerates STANDARD module capabilities from source for documentation
  purposes - browser-free, OSM-primary, produces a feature-catalog artifact.

**Discriminator**: custom/bespoke code in a client instance -> **`odoo-customization-inventory`**.
Standard Odoo source capabilities for docs -> **`odoo-doc-feature-map`**.

If the user said "give me an inventory of all the custom code we've built on top of Odoo" ->
`odoo-customization-inventory` (engagement artifact).
If the user said "enumerate all features that stock module ships for the docs" ->
`odoo-doc-feature-map` (standard source for documentation).

## Collision 15 - doc-walkthrough vs acceptance vs content-draft vs solution-design

**Prompt**: "write scenarios", "create walkthroughs", "document how to use this module".

- `odoo-doc-walkthrough`: authors happy-path TEXT scenarios for USER DOCUMENTATION - narrative
  prose + structured steps[], browser-free, no execution, not bound by acceptance oracle contract.
- `odoo-acceptance`: drives a LIVE Odoo instance/UI to execute an independent oracle and
  adjudicate PASS/FAIL/UNVERIFIED with evidence. Requires a live instance + browser MCP.
- `odoo-content-draft`: marketing copy (landing page / email sequence / social / blog) with
  `[Image:]` markers for illustrators; audience is external prospects, not end-users.
- `odoo-solution-design`: technical architecture DOCUMENT (data model / override strategy /
  module structure) produced BEFORE implementation is written; no user-facing narrative.

**Discriminator**: documentation narrative, no execution -> **`odoo-doc-walkthrough`**.
Live drive + PASS/FAIL verdict -> `odoo-acceptance`. Marketing copy + channels ->
`odoo-content-draft`. Technical architecture pre-code -> `odoo-solution-design`.

If the user said "write a step-by-step guide for users on how to use the purchase flow" ->
`odoo-doc-walkthrough` (text docs, no browser).
If the user said "run the purchase flow on the real instance and tell me if it passes" ->
`odoo-acceptance` (live execution + verdict).
If the user said "write blog post copy explaining the purchase module for prospects" ->
`odoo-content-draft` (marketing copy).
If the user said "design the architecture for the new purchase approval flow before we code it" ->
`odoo-solution-design` (technical architecture).

## Collision 16 - icon-design vs screenshot-crop vs in-UI glyph

**Prompt**: "icon", "image for the module", "glyph", "create the module icon".

- `odoo-icon-design`: DESIGN and GENERATE the module's `icon.png` (256x256 App Store de-facto)
  via SVG code-gen + rasterizer; brand-aware, version-gated (PNG-only v8-v18; +icon.svg +
  manifest key on v19); standalone-first, browser-free.
- `odoo-doc-illustration` (screenshot crop): captures a live Odoo screen at a viewport crop -
  used as a fallback illustration in docs, NOT a designed icon; output is a screenshot, not
  an SVG-derived asset file.
- In-UI glyph: a Font Awesome class name used in a `<button>` or field `widget` declaration
  in views or buttons - it is NOT a file asset; route to `odoo-coding`.

**Discriminator**: design/generate the `icon.png` asset file -> **`odoo-icon-design`**.
Capture a live screen crop for docs -> `odoo-doc-illustration`. Font Awesome class name in
a view -> `odoo-coding`.

If the user said "create the icon.png for our new purchase_custom module" ->
`odoo-icon-design` (design + generate asset).
If the user said "take a screenshot of the purchase list view for the module docs" ->
`odoo-doc-illustration` (live screen crop).
If the user said "add a shopping-cart icon to the Purchase button in the form view" ->
`odoo-coding` (Font Awesome class in XML view).
