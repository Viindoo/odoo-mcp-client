# odoo-marketer - MODE copy

## Channels (`copy`)

| Channel | Length and shape | Call to action |
|---|---|---|
| LinkedIn post | 150-300 words; one-sentence hook, insight or story, reflection question | an open question; no link unless critical; 3-5 hashtags |
| Blog article | 800-1,500 words; H2: Intro, Problem, Solution, How it works, Outcome, Conclusion; `[Link: X]` placeholders | "Start a free trial" or "Book a demo" button text in the last paragraph, localized |
| YouTube script | 3-5 min (450-750 spoken words); Hook 0:00-0:15, Problem 0:15-1:00, Solution 1:00-3:00, demo cue 2:00-3:00, CTA 3:00-3:30, Outro | verbal: subscribe, link in description, a comment question; `[NOTE: show screen of X]` cues; a real screencast is `odoo-demo-recording` |
| Email sequence | 3-5 emails, Day 0 / 2 / 7 / 14 / 21, 150-250 words each; subject, 45-char preview, body | one `[LINK: ...]` per email; an A/B subject variant |
| Landing-page copy | one `<!-- <KEY> -->` block per copy-sourced key of `${CLAUDE_PLUGIN_ROOT}/skills/odoo-doc-illustration/references/app-store-template.md` § Section Map, in its order, within its targets (three WHAT-CHANGES blocks, five FAQ entries), each answering a pain or pillar of the buyer profile, with `[Image: <slug>]` markers; copy only, no HTML | none - the store renders its own button |
| Social caption | 60-100 words for Facebook or Zalo; conversational, at most two emoji, an SME scenario | a question or a soft "message us" nudge; hashtags |

## MODE copy

1. **Inputs.** Channel, topic, audience, language and tone from the brief; what it leaves open is
   ONE compound question at most, answered before drafting; a clear enough brief is drafted at
   once with the assumptions stated. Then § Before you write and § Buyer profile.
2. **Draft** per the channel row: hook or headline, one or two key claims, their evidence, the
   call to action; placeholders in brackets (`[Image: dashboard-mrp]`, `[Link: free-trial-page]`).
3. **Self-review**, fixed inline before you return: voice rules kept; at least one specific or
   abstract-template data point; the CTA matches the channel (a landing page has none); a landing
   page traces every block to a pain or a pillar of the profile and names who it is for; no
   invented name, number or ROI; the length and the item counts of the channel row; no internal
   path, roadmap or confidential detail; every `<TBD>` listed in `concerns`.
4. **Save** the draft as `<SHARE_DIR>/content/<topic-slug>-<channel>-<YYYY-MM-DD>.md` (an updated
   hit keeps its file) and return its path and the draft.
