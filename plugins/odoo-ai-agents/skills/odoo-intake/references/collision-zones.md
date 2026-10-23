# Intake - Collision Zones

**Contents:** Collision 1 - Objection vs Capability Proof - Collision 2 - Version Diff vs Feature Highlights - Collision 3 - Deprecation Audit vs Version Diff - Collision 4 - Deal Follow-up vs Objection Handler - Collision 5 - Skill vs Command (same domain) - Collision 6 - Capability Proof vs Demo Recording - Collision 7 - Coding vs Debug - Collision 8 - BRL vs Gap Analysis vs Single Feature - Collision 9 - Parallel multi-change delivery vs BRL vs Coding - Collision 10 - Doc Illustration / Doc Site vs Demo Recording - Collision 11 - Rebase vs Forward-Port vs Parallel multi-change delivery - Collision 12 - Modules-Upgrade vs Forward-Port vs Plan-Upgrade vs Deprecation-Audit vs Version-Diff - Collision 13 - feature-check vs doc-feature-map vs feature-highlights - Collision 14 - customization-inventory vs doc-feature-map - Collision 15 - doc-feature-map vs acceptance vs content-draft vs solution-design - Collision 16 - icon-design vs screenshot crop vs in-UI glyph - Collision 17 - DOC LAYER vs module-packaging - Collision 18 - code-review vs perf-audit vs security-audit vs debug - Collision 19 - rfp-response vs gap-analysis vs capability-proof vs /odoo-respond-bid - Collision 20 - test-writing vs qa-suite vs acceptance - Collision 21 - customer-health vs discovery-summary vs pricing-proposal vs deal-followup - Collision 22 - module docs vs docs site vs both

Load this when two candidate skills overlap and the Routing Table's **Discriminator** column
does not break the tie. Pick by the discriminator; when it is still undecidable, ask the user with
both names and the one-line difference.

## Collision 1 - Objection vs Capability Proof

- `odoo-objection-handling`: a customer-facing paragraph to paste ("write a response", "customer says Odoo can't").
- `odoo-capability-proof`: a technical evidence package (modules + code + demo steps).

"write a response" -> objection. "technical evidence for the demo" -> capability-proof.

## Collision 2 - Version Diff vs Feature Highlights

- `odoo-feature-highlights`: "slide", "newsletter", "summarize for business".
- `odoo-version-diff`: "which APIs changed", a dev audience.

## Collision 3 - Deprecation Audit vs Version Diff

- `odoo-deprecation-audit`: scans OUR code ("what will break", "audit before upgrading").
- `odoo-version-diff`: a clean diff between versions with no code scan ("what's different between two versions").

## Collision 4 - Deal Follow-up vs Objection Handler

- `odoo-deal-followup`: "hasn't replied", re-engagement email.
- `odoo-objection-handling`: a counter to a stated objection.

## Collision 5 - Skill vs Command (same domain)

No slash prefix and a single-step intent -> the SKILL. An explicit slash command goes to the command directly (intake is not consulted). "Synthesize and save it to disk" -> recommend the COMMAND for the save step.

## Collision 6 - Capability Proof vs Demo Recording

- `odoo-capability-proof`: written proof or RFP evidence the rep can paste.
- `odoo-demo-recording`: a real recorded video/GIF ("record", "video", "screencast", "GIF").

"demo" alone: ask "written evidence package, or a recorded video of the flow?"

## Collision 7 - Coding vs Debug

- `odoo-debug`: a symptom plus "why / not showing / isn't working" - cause first.
- `odoo-coding`: write from scratch, or write the fix once the cause is known.

## Collision 8 - BRL vs Gap Analysis vs Single Feature

- 1 feature -> `odoo-feature-check`.
- Short ad-hoc list (under ~20 items), no cost/DAG/RTM -> `odoo-gap-analysis`.
- Hundreds to thousands of items, OR an explicit cost estimate, dependency graph or RTM -> `odoo-brl` (an explicit RTM or cost signal overrides a small count).
- Count not stated: ask "How many requirements? Tens or more with cost/traceability needs -> odoo-brl; a short ad-hoc list -> gap-analysis."

## Collision 9 - Parallel multi-change delivery vs BRL vs Coding

- `odoo-planning`: "parallelize N changes", "land N related changes as one reviewed PR". It plans the nodes; the main agent runs the approved plan (`plan-mode-schema.md` § Running the plan) and stops at "PR opened"; the merge belongs to `odoo-pr-monitoring`. Never route a user prompt to an executor.
- `odoo-brl`: classify and cost requirements (RTM/cost/DAG); writes no code, touches no git.
- `odoo-coding`: ONE change (backend and/or frontend), no git orchestration.

## Collision 10 - Doc Illustration / Doc Site vs Demo Recording

Deliverable is a DOCUMENT (text + still images) -> `odoo-doc-illustration` (module) or `odoo-doc-site` (site), per § Documentation routing. Deliverable is a playable recording ("video", "quay", "GIF") -> `odoo-demo-recording`. "demo" with no qualifier: ask "static screenshot doc, or recorded video?"

## Collision 11 - Rebase vs Forward-Port vs Parallel multi-change delivery

- `odoo-git-rebase`: SAME Odoo series, one branch's whole commit range replayed onto a new base.
- `odoo-forward-port`: commits (one, or a whole range) ported UP a major, absorbed by ONE no-ff merge. Its only shape is the merge; "one-shot" in a brief means one run, never a cherry-pick.
- `odoo-planning`: many disjoint changes landed together as one PR per repo.

## Collision 12 - Modules-Upgrade vs Forward-Port vs Plan-Upgrade vs Deprecation-Audit vs Version-Diff

- `odoo-modules-upgrade`: execute a cross-major cluster upgrade at code level (installable and working, core-absorbed modules deleted, mergeable PR).
- `odoo-plan-upgrade`: plan and risk overview only, no code.
- `odoo-forward-port`: commits moved UP a major.
- `odoo-deprecation-audit`: detection report only.
- `odoo-version-diff`: API delta between two versions only.
- Code upgrade vs database migration: `odoo-modules-upgrade` upgrades the modules' code and never touches a database; moving a database to a higher series is never executed by the plugin, and only its custom-module scripts are written, by `odoo-data-migration`.

## Collision 13 - feature-check vs doc-feature-map vs feature-highlights

- `odoo-feature-check`: ONE yes/no availability question.
- `odoo-doc-feature-map`: enumerate ALL features of a module for docs, plus role map and usage walkthrough text.
- `odoo-feature-highlights`: marketing "what's new in version X".

## Collision 14 - customization-inventory vs doc-feature-map

- `odoo-customization-inventory`: CUSTOM code in a client instance, for an engagement deliverable.
- `odoo-doc-feature-map`: STANDARD module capabilities from source, for documentation.

## Collision 15 - doc-feature-map vs acceptance vs content-draft vs solution-design

- `odoo-doc-feature-map`: documentation narrative, no execution; with screenshots in the module guide -> `odoo-doc-illustration`.
- `odoo-acceptance`: runs a live instance/UI and adjudicates PASS/FAIL/UNVERIFIED.
- `odoo-content-draft`: marketing copy for external prospects.
- `odoo-solution-design`: technical architecture before code.

## Collision 16 - icon-design vs screenshot crop vs in-UI glyph

- `odoo-icon-design`: design and generate the `icon.png` file.
- `odoo-doc-illustration`: a live screen crop used as a docs illustration.
- Font Awesome class name in a view or button -> `odoo-coding`.

## Collision 17 - DOC LAYER vs module-packaging

- `odoo-doc-illustration`, DOC LAYER omitted or "both guide and store page" -> `both` (default); "user guide only / doc/index.rst" -> `userguide`; "App Store page only / static/description/index.html" -> `appstore`.
- `module-packaging` (workflow, row 53): explicit icon.png, manifest audit, or store submission.

## Collision 18 - code-review vs perf-audit vs security-audit vs debug

- A single explicit lens ("just the perf" / "just security") -> `odoo-perf-audit` / `odoo-security-audit`.
- "review this / okay to ship / anything to worry about", no single lens -> `odoo-code-review`.
- A live runtime symptom ("timing out on the live server", traceback) -> `odoo-debug`.
- Write the fix -> `odoo-coding`.

## Collision 19 - rfp-response vs gap-analysis vs capability-proof vs /odoo-respond-bid

- "compliance matrix / rate against Odoo / tender scoring" -> `odoo-rfp-response` (no cost).
- "effort + cost estimate" -> `odoo-gap-analysis` (`odoo-brl` at hundreds-of-items scale).
- "prove ONE requirement with code" -> `odoo-capability-proof`.
- "the whole bid response" -> `/odoo-respond-bid`.

## Collision 20 - test-writing vs qa-suite vs acceptance

- "write test_*.py / a tour / Hoot" -> `odoo-test-writing` (runnable files).
- "a test-PLAN doc / release QA checklist" -> `odoo-qa-suite` (nothing runs).
- "run it for real and tell me pass/fail" -> `odoo-acceptance`.

## Collision 21 - customer-health vs discovery-summary vs pricing-proposal vs deal-followup

- Existing customer at risk or renewal -> `odoo-customer-health`.
- New prospect meeting notes -> `odoo-discovery-summary`.
- A quote or price -> `odoo-pricing-proposal`.
- "hasn't replied, write a follow-up" -> `odoo-deal-followup`.

## Collision 22 - module docs vs docs site vs both

Decide TARGET by § Documentation routing of `SKILL.md`; when a site row exists, that rule decides before any single-skill row.

- "update the docs site page" -> `odoo-doc-site`.
- "forward-port the docs of PR #N": recon checks which repository PR #N belongs to - a declared docs-site repo -> `odoo-doc-site` with PORT; an addons repo, even when the PR changes only `doc/` files -> `odoo-forward-port`.
- "document the module with screenshots" -> `odoo-doc-illustration`, invoked directly (no `odoo-planning` hop).
- "ship the field and document it" -> `odoo-planning` with `docs-module` and `docs-site` tail nodes kept or dropped by the facts.
