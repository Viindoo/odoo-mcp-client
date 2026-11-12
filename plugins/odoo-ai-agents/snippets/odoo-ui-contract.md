# Odoo UI contract

Binds whoever designs, writes, reviews or accepts a change that touches a screen. A change
**touches a screen** when it adds or changes a view arch, a QWeb template, a stylesheet, a client
component or field widget, a report layout, or a website or portal page.

## 1. Paint with core levers only

A theme restyles Odoo by overriding what core of the series provides: its view elements and field
widgets, its components, its classes, its SCSS variables and mixins. Anything a module paints by
itself is out of every theme's reach.

- A new class, id or `name` identifies an element for code, tests and xpath. It carries no colour,
  size, font or spacing rule.
- A stylesheet is written only when no view attribute, widget, class or component of core gives
  the result. Every value in it is a core SCSS variable, or a core mixin or function applied to
  one.
- A control uses the markup and classes of the same control in core: a button, a badge, a card, a
  dropdown, an empty state.
- The test: a theme changes one core variable and the module follows, with no edit in the module.

Which variables, classes and components exist is a fact of the series. Read it from the index
(the stylesheets of `web`, where a variable is defined and overridden) or the checkout, never
from memory or from another series.

## 2. Both colour schemes

Applies on a series whose `web` manifest declares a dark asset bundle. That bundle is the same
stylesheets compiled again with a theme's dark variable values, plus the `*.dark.scss` files. A
screen that follows § 1 is therefore dark-ready, and what breaks it is a value fixed to one
scheme:

- a literal colour (hex, `rgb()`, `hsl()`, a colour name) in a stylesheet, a `style` attribute, a
  template or JavaScript;
- a class that fixes a scheme whatever the theme (`bg-white`, `bg-light`, `text-dark`,
  `text-white`, `border-light`); core's own classes follow the variables (`bg-view`, the numbered
  gray backgrounds, `text-muted`, `text-body`, the `text-bg-<status>` pairs);
- a tint mixed with white or black; mix two core variables;
- an image or icon with a fixed fill that sits on a themed surface; its source or filter comes
  from a custom property of the component;
- a colour computed in JavaScript (a chart); core's colour helpers take the scheme.

Where no core variable fits, use core's pattern: the rule reads a custom property scoped to the
component, with a core variable as its fallback, and a `<name>.dark.scss` beside the stylesheet
holds only the override of that property. The manifest removes the module's `*.dark.scss` from
the light backend bundle and adds them to the dark one. A dark file that holds anything but
property overrides is a defect.

## 3. Lay out for the person entering data

- The view type fits the job: a list to scan and compare, a kanban to triage by stage, a form to
  work on one record.
- A form reads in the order its user thinks and types. Identifying fields come first, then what
  is filled on every record, then what is rare or technical (a notebook page). Read-only figures
  come last or sit in a smart button.
- At most two `<group>` columns, grouped by meaning. A third column truncates labels.
- A standard field widget before a custom one: it brings keyboard use, accessibility, translation
  and the theme.
- Phone first. Core lays the arch out as one column there, so the order of the arch is the order
  on a phone and its first screenful holds what the user needs first. No fixed pixel width.
- A list shows at first glance only the columns needed to pick a record; the others are optional
  and hidden.
- An extension is judged on the whole rendered screen, never on the inherited fragment.

## 4. Look at what you changed

Odoo builds a screen from a chain of inherited views, patches and asset bundles, so the arch or
rule you wrote is not what renders. Whoever writes or fixes a change that touches a screen, after
the build:

1. Opens each changed screen on the instance as a user of the role it serves, on a record with
   realistic data, in every state its mockup shows (empty, a new record, after the main action);
   with no mockup, in every state the change affects.
2. Captures every changed screen, in each of those states, at the desktop AND the phone width of
   `${CLAUDE_PLUGIN_ROOT}/docs/odoo-ui-knowledge.md` § Responsive breakpoints, with the console messages.
3. Tries the dark scheme, in this order: the appearance switch the theme puts in the user menu
   or the systray (a moon or sun icon, an "Appearance" or "Dark mode" entry); only where there
   is none, the `color_scheme` cookie set to `dark` on the instance's own origin and a reload.
   The scheme is dark when the page loads the dark asset bundle: captures each changed screen
   again at both widths, one state each.
   Otherwise reports `dark: static check only`, naming what was tried.
4. Builds one contact sheet per width, so a desktop capture stays legible beside a tall phone
   one: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/lib/image_sheet.py sheet --out sheet-desktop.png --col-width 800
   --columns 2 --inputs <desktop captures>` and `--out sheet-phone.png --col-width 375
   --columns 4 --inputs <phone captures>`.
5. Opens the sheets and looks: a truncated label, a misaligned or orphaned field, empty space, an
   element unlike its core neighbour, the wrong thing first on the phone, a difference from the
   mockup.
6. Fixes and captures again until the screen is right. Its return lists, per changed screen and
   state, the desktop and the phone capture, then the two sheets and the `dark:` line.

A reviewer or tester rules on a screen from captures of the running instance, never from the
source alone.

## 5. Mockups

A mockup binds what the module decides: the view type, the fields and actions a screen holds,
their order and grouping, the module's own wording, its states and behaviour, and what a phone
shows first. What core or the theme renders by itself is illustration: the navbar and the control
panel, where the search and its facets sit, how header buttons and the statusbar are laid out at
each width, the frame of an empty state, every colour, font and pixel size. It differs by series
and by theme, and the running instance is right. Conformance is
therefore judged by structure (the same regions, order and groups; the same first screenful on a
phone) and style is judged the core way: the element uses the class or component of its core
counterpart and its computed values equal those of a neighbouring core control. A colour code or
a pixel measure is never compared. A difference that a line of the module's arch, template or
stylesheet governs is a finding. A difference no line of the module governs is core's rendering:
it is noted against the design, never raised against the module and never sent to its coder.
