# JS and tour framework reading

- **JS:** `js_test_inspect(module='<module>', odoo_version='<version>')` first - Hoot and QUnit
  both ship on some series and the mix varies by module (`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` row 2) - then
  `find_test_examples(query='<framework> describe test', kind='js', odoo_version='<version>')` for
  that framework. Which suite classes run them (desktop and mobile) and how a test sets a touch or
  non-touch device: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/coding_guidelines/<version>/tests.md` § JavaScript unit tests.
- **Tour:** `js_test_inspect(module='web_tour', odoo_version='<version>')` for the registry path
  and step shape, then `find_test_examples` for real steps.
