> Source: official Odoo 14.0 coding guidelines - https://raw.githubusercontent.com/odoo/documentation/14.0/content/contributing/development/coding_guidelines.rst

# CSS coding guidelines

- Prefix all your classes with *o_<module_name>* where *module_name* is the technical name of the module ('sale', 'im_chat', ...) or the main route reserved by the module (for website module mainly, i.e. : 'o_forum' for *website_forum* module). The only exception for this rule is the webclient: it simply uses *o_* prefix.
- Avoid using *id* tag
- Use Bootstrap native classes
- Use underscore lowercase notation to name class
