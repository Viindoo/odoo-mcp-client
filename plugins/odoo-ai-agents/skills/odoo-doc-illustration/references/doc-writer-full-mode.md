# odoo-doc-writer - MODE full and updates

## Update (CHANGE is a feature list)

A run with `CHANGE` as a feature list updates the existing documents instead of rewriting them.
`whole`, or no `CHANGE`, is a first-time run.

1. **Map.** Match each `CHANGE` line to a catalog capability by name or menu path (a given catalog is
   read; refresh only the entries of the changed capabilities and keep every `feature_id`). Find the
   sections of `doc/index.rst` that describe those capabilities, and the images
   each embeds. Sections about unchanged capabilities and their images are out of the run.
2. **Shot list** holds only the shots of the mapped sections, plus the shots a new capability needs;
   the cover is recaptured only when a mapped capability appears on it.
3. **Write** only the mapped sections, in every language file, the same section in each; a section
   of an unchanged capability stays byte-identical. A rewritten section describes the behaviour as
   it is, for a reader who never saw the previous text: no "previously", no account of the fix
   that caused the rewrite (`${CLAUDE_PLUGIN_ROOT}/snippets/artifact-voice.md`). A removed capability loses its section and its
   images; add a section for a new capability in the process order of `role-map.json`.
4. **Gates** run on the whole file as in MODE full steps 6-7.

## MODE full

1. **Shared files.** Run MODE catalog-only for every file the brief does not supply. With `CHANGE`
   as a feature list, follow § Update for steps 1-5.
2. **Readers.** The roles of `role-map.json`; the SRS or Domain line names the same people in
   business terms - use those names. Without a non-admin role the guide has one chapter
   "Using <module>" and the report carries `concerns: [no non-admin role]`.
3. **Shot list before any capture.** Per `CAPTURE MODE`: `screens` - one screen per task the
   guide documents; `scenarios` - one still per walkthrough step. For each shot: slug, target
   file, slot and its measured width, framing and required context, per
   `${CLAUDE_PLUGIN_ROOT}/skills/_shared/doc-capture-mechanics.md` § 7.
4. **Capture** every shot per doc-capture-mechanics (family and mode § 1-2, staging § 3, the handle
   § 4, instance § 5, on-theme check § 6, the step loop § 8-9, locales § 10, the coverage report § 11,
   degraded paths § 12). In `scenarios` mode drive each step as the scenario's role. Before the
   first chapter of a role, open its menus once as a user holding ONLY that role (the role map's
   group): a menu that role cannot reach is not in its chapter, whatever the catalog inferred.
5. **Write `doc/index.rst`** (English) and `doc/index_<locale>.rst` per other locale, prose and
   headings in that locale, labels EXACTLY as the UI shows them in that locale - read from the
   screen you captured or the view on disk, never paraphrased from the English; a label you could
   not read in a locale is a `concerns` line and the file is not returned as DONE until it is read.
   Stamp every catalog row's `coverage` (`guide`, `setup`, or `excluded: <reason>`) as you place
   it; `full-guide` means every row is stamped (the caller runs `doc_coverage_check.py`). Skeleton, in order:
   1. *Overview* - the business problem (manifest summary, catalog `value`s); the process as its
      stages with the acting role and the hand-off (`role-map.json` `process`); a table Role |
      What they do | Access right to assign (`ui_name`).
   2. *Setup (for the Administrator)* - installation (Apps, search, Install, the required apps by
      their user-facing names), configuration by UI label, assigning each role its access right.
   3. *One chapter per role*, "<Business role>: <job>", in the order the roles first act in the
      process; each task a sub-section with numbered steps and its image, from the walkthrough
      scenarios of that role. A role that implies another covers only what it adds.
   4. *Troubleshooting* and *FAQ* - `full-guide` only.
   After the title, one `.. note::` per `extends_in_scope` base: "Extends <base> - see its
   documentation", linked per `${CLAUDE_PLUGIN_ROOT}/snippets/module-doc-references.md` § Links
   to another module. Images: `.. image:: assets/<file>` with the class and `:width:` of that
   snippet § Images; `:alt:` is the task in words. Every rule of
   `${CLAUDE_PLUGIN_ROOT}/snippets/rst-validity-contract.md` applies.
6. **RST gate.** Render every `doc/*.rst` you wrote:

   ```
   python3 -c "import docutils" 2>/dev/null || echo DOCUTILS_UNAVAILABLE
   ```
   Unavailable and `python3` is not a virtualenv (`sys.prefix == sys.base_prefix`): one
   `python3 -m pip install --user docutils`; still unavailable -> `NEEDS_CONTEXT(docutils for the
   plugin python3)` listing the files written. Then per file:

   ```
   python3 - <file> <<'EOF'
   import sys, docutils.core
   from docutils import nodes
   doc = docutils.core.publish_doctree(open(sys.argv[1], encoding="utf-8").read(),
                                       settings_overrides={"report_level": 1, "halt_level": 5})
   msgs = [m.astext() for m in doc.findall(nodes.system_message)]
   print("\n".join(msgs)); sys.exit(1 if msgs else 0)
   EOF
   ```
   Exit 1: fix the file and re-run. You never return a file that exits 1.
7. **Finals and reference gate.** `mv` each final into `static/description/assets/` under its
   convention name and optimise it (doc-capture-mechanics § 13), bring every off-convention reference of the files you
   wrote into the convention, then run the gate of `module-doc-references.md` § Reference gate
   (`--series` = the resolved `ODOO VERSION`) on every `doc/*.rst` you wrote until it exits 0; exit 2 is
   `NEEDS_CONTEXT` with the printed remedy.
8. **Close every page** you drove (`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md`
   T2), then report. Keep the catalog, the shot list and the staged captures.
