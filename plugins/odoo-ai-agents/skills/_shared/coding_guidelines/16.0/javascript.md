> Source: official Odoo 16.0 coding guidelines - https://raw.githubusercontent.com/odoo/documentation/16.0/content/contributing/development/coding_guidelines.rst

# Javascript

## Static files organization

Odoo addons have some conventions on how to structure various files. We explain here in more details how web assets are supposed to be organized.

The first thing to know is that the Odoo server will serve (statically) all files located in a *static/* folder, but prefixed with the addon name. So, for example, if a file is located in *addons/web/static/src/js/some_file.js*, then it will be statically available at the url *your-odoo-server.com/web/static/src/js/some_file.js*

The convention is to organize the code according to the following structure:

- *static*: all static files in general

  - *static/lib*: this is the place where js libs should be located, in a sub folder. So, for example, all files from the *jquery* library are in *addons/web/static/lib/jquery*
  - *static/src*: the generic static source code folder

    - *static/src/css*: all css files
    - *static/fonts*
    - *static/img*
    - *static/src/js*

      - *static/src/js/tours*: end user tour files (tutorials, not tests)

    - *static/src/scss*: scss files
    - *static/src/xml*: all qweb templates that will be rendered in JS

  - *static/tests*: this is where we put all test related files.

    - *static/tests/tours*: this is where we put all tour test files (not tutorials).

## Javascript coding guidelines

- `use strict;` is recommended for all javascript files
- Use a linter (jshint, ...)
- Never add minified Javascript Libraries
- Use camelcase for class declaration

More precise JS/OWL guidelines incl. web tooling (ESLint/Prettier) are in the local canonical copy: `../javascript-coding-guidelines.md`. You may also have a look at existing API in Javascript by looking Javascript References.
