> Source: official Odoo 17.0 coding guidelines - https://raw.githubusercontent.com/odoo/documentation/17.0/content/contributing/development/coding_guidelines.rst

# JavaScript Guidelines

## Static files organization

The Odoo server will serve (statically) all files located in a `static/` folder, but prefixed with
the addon name. For example, a file at `addons/web/static/src/js/some_file.js` will be statically
available at `your-odoo-server.com/web/static/src/js/some_file.js`.

### Recommended directory structure

```
static/
  static/lib/               - JS libs, each in a sub-folder
                              e.g. addons/web/static/lib/jquery/
  static/src/               - generic static source code folder
    static/src/css/         - all CSS files
    static/fonts/
    static/img/
    static/src/js/
      static/src/js/tours/  - end user tour files (tutorials, not tests)
    static/src/scss/        - SCSS files
    static/src/xml/         - all QWeb templates rendered in JS
  static/tests/             - all test related files
    static/tests/tours/     - tour test files (not tutorials)
```

---

## JavaScript coding guidelines

- `use strict;` is recommended for all JavaScript files
- Use a linter (jshint, ...)
- **Never add minified JavaScript Libraries**
- Use Pascal case for class declaration

More precise JS guidelines are detailed in the
[Odoo GitHub wiki](https://github.com/odoo/odoo/wiki/Javascript-coding-guidelines). You may also
have a look at existing API in Javascript by looking at Javascript References.
