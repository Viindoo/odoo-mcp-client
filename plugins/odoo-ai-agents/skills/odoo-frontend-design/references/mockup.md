# Screen mockups

A design that touches a screen (`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-ui-contract.md`) shows the
screen before anyone builds it, so the approver, the coder and the reviewer look at the same
thing. How the mockup binds: § 5 of that contract.

## Which of the two

- **Mockup** - the change adds a screen, a component, a report layout or a page, or rearranges an
  existing screen (moves, regroups or removes what is there).
- **Placement note** - the change only adds elements to an existing screen.

## Placement note

Capture the current screen at the desktop width on a running instance; with no instance, write
`source: arch` and work from the merged arch. Then one row per new element: the slot it goes in
and the neighbour it follows, its label, its widget, when it is visible. No HTML.

## Mockup

Files, under `<SHARE_DIR>/designs/<slug>/mockups/`:

| File | Content |
|---|---|
| `<screen>.html` | the screen: a copy of `${CLAUDE_PLUGIN_ROOT}/skills/odoo-frontend-design/assets/mockup-skeleton.html` that keeps its `<head>`, toolbar and script, with the sample screens replaced by yours, built from the same `mk-` classes |
| `mockup-kit.css` | a copy of the kit stylesheet from the same `assets/` directory, so the page opens on its own |
| `<screen>-desktop.png`, `<screen>-phone.png` | full-page captures at the desktop and the phone width of `${CLAUDE_PLUGIN_ROOT}/docs/odoo-ui-knowledge.md` § Responsive breakpoints |
| `<screen>-desktop-dark.png`, `<screen>-phone-dark.png` | the same with `?scheme=dark` |
| `sheet.png` | one contact sheet of all captures: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/lib/image_sheet.py sheet --out sheet.png --col-width 400 --columns 4 --inputs <captures>` |

Every capture adds `tools=off` to the address, which hides the page's own toolbar.

Rules:

- **Real content.** Labels in the language of the screen's users, realistic sample values, and
  the states that matter to the job: empty, filled, after the main action, in error.
- **The order is the design.** Blocks and fields stand in the order the user enters data; the
  phone capture shows what comes first.
- **Behaviour is shown, not described.** Where the screen does more than core does by itself (a
  field that appears on a choice, a step of a wizard, a dialog), a few lines of inline script
  make the HTML do it. The page takes `?state=<name>` (the skeleton's script puts it on the root
  as `data-state`), and each state is captured as `<screen>-<state>-desktop.png` and `-phone.png`.
- **Every block names its core counterpart** in a note (`mk-note`): the view element, widget,
  component or class of the target series the coder will use. A block with no counterpart is a
  custom element: the design lists it with the reason it is needed.
- **Header buttons fold on a phone, as in core.** The kit hides them there behind its `Actions`
  control; keep that control in the header, or the main action vanishes from the phone capture.
- **The kit's look only.** No colour, font or size is added to the kit. A mockup that restyles it
  promises a look that belongs to the theme.
- **Look at it.** Open the page in the browser, capture, open the captures, and fix what reads
  badly at either width or in either scheme before the design goes to its gate. A browser that
  refuses a `file://` address is served the directory over localhost for the capture.

## In the design document

`## Screens` holds one block per screen: the role and its job, the view type, the mockup files or
the placement note, what the phone shows first, and the custom elements with their reasons. The
design gate names `sheet.png` so the approver sees the screen before answering.
