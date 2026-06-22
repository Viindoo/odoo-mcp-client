> Source: https://github.com/odoo/odoo/wiki/Javascript-coding-guidelines (snapshot 2026-06-22; the upstream wiki may change at any time). Version-agnostic per Odoo ("Since v15... forward ported").

Since v15 has been released, the following guidelines apply (even for fixes in older versions, as they will be forward ported)

# Tooling

We provide tooling in the web module to lint and prettify files that you have changed automatically on commit, this tooling can be enabled using `/web/tooling/enable.sh`, which does the following things:
* Copy our eslint and prettier config to the root of your repository.
* Install the node modules required to lint your code.
* Changes your git config's `core.hooksPath` to point towards `/web/tooling/hooks` to enable our pre-commit hook.

Make sure that the node version that you're using is up to date, some popular linux distros have a tendency to only have wildly out of date (sometimes no longer supported) versions of node in their official repos. Some of the modules used by the tooling rely on recent JavaScript features and the tooling will simply crash if your node version is too old.

The pre-commit hook does the following:
* Check if your current branch name starts with "master". If not, the pre-commit hook does nothing. See the note further down as to why we do not lint files in stable.
* Check if the package.json at the root of the repository is up to date with the one in the tooling folder, if not, it reloads the tooling (disables it and enables it again)
* Check if the config files are up to date (.eslintignore, .prettierignore, .eslintrc.json, .prettierrc.json) with those in the tooling folder, if they are not, it overwrites them with the latest version. This also means that any changes you make to those files will be lost as soon as you try to commit.
* Prettifies and lints all files that are staged (not just the lines that were touched). If there are any linting errors that cannot be fixed automatically, the files are reverted to their original state before the commit, the commit is aborted, and linting errors are displayed so you can fix them by hand.

If for some reason you need to bypass the pre-commit hook, for example because you're working on something which is not valid yet, but want to make a temporary commit to switch branches, you may do so by using `git commit --no-verify`. Amending this commit at a later point will run the pre-commit again.

By default, all files are ignored, and we whitelist modules or parts of modules as we modernize the corresponding code. This also means that unless you're working in a module which is whitelisted, the tooling will not be active. If you're working in an official Odoo module and would like to enable the tooling for that module or some parts of it, you may submit a PR to add it to the whitelist (by changing the `_prettierignore.json` and `_eslintignore.json` in `/web/tooling`) to the js-framework team. If you're working in a custom module, you can simply add an empty `.prettierignore` and `.eslintignore` file at the root of your module.

While this is handled automatically by the pre-commit hook, if you're linting files by hand, **DO NOT LINT EXISTING FILES IN STABLE VERSIONS**. Linting files in stable creates noise in the diff and inevitably creates conflicts during forward-ports, both of the linting changes and of future changes in previous version that would affect those same lines. As always, keep diffs in stable minimal, just make sure that the lines you're modifying don't introduce linting errors after they've been forward ported.

All guidelines which are enforced by the tooling will not be mentioned explicitly.

# General guidelines:

* Use [ES6 Odoo modules](https://www.odoo.com/documentation/master/developer/reference/frontend/javascript_modules.html#frontend-modules-native-js) in new code.
* Avoid introspection when possible: don't dynamically build a method name to call it. It is more fragile and more difficult to refactor.
* Write unit tests.
* Prefer named exports over default exports, it makes navigating the code easier as named exports can't be aliased implicitly.
* Always call the super method in method overrides (`super.methodName(...arguments)` in ES6 classes and components, `this._super(...arguments);` in old-style classes like widgets).
  * Exception: do not call super methods in components that extend `owl.Component` directly. `setup` is guaranteed to be empty on `owl.Component`, and `render` and `constructor` should not be overriden.
* Do not propagate references to owl component instances anywhere. Owl is responsible for components' lifecycle. All methods on owl components should be considered private. Components can choose to expose methods by passing them explicitly to whoever needs them.
* When declaring methods (functions that need `this`) in plain objects, prefer the [method definition](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Functions/Method_definitions) syntax.
* Do not write templates of component in javascript files using `owl.xml`, extract the template to a separate xml file that lives next to the js file.
* Treat objects and functions from owl as an import, and destructure them at the top of the file right after your imports:
```js
import { a } from "@module/file";

const { Component, useState } = owl;
``` 
* Do not use the value of an assignment expression for anything, assignments should always be their own statement:

Instead of: 
```javascript
if (myVariable = value) {...}
return (myVariable = value);
myFunction(myVariable = value);
```
Use: 
```javascript
myVariable = value;
if (value) {}
return value;
myFunction(value);
```
# Documentation

* Use JSDoc comments to document your functions and methods (see http://jsdoc.app).
* For method overrides, use the `@override` tag in the JSDoc. You may mention which parent class' method is overridden:

```javascript
    /**
     * When a save operation has been confirmed from the model, this method is
     * called.
     *
     * @override method from FieldManagerMixin
     * @param {string} id
     */
    confirmSave(id) {
```

* There should be an empty line between the main function comments and the tags,
  or parameter descriptions

# Deviations from previous guidelines

* We no longer distinguish between technical and non-technical string with their quote types: use double quotes for all strings (such as `"Hello"`), unless they would require escaping quotes, in which case you may use the single quotes (eg: `'He said "I love you"'`) or a template string  (`` `don't say "yes" too quickly` ``). This is enforced by the eslint config.
* We no longer recommend private methods' name start with an underscore. All methods are considered private on components, if you're writing a non-component class and you need a private method, consider extracting it to a utility function that's captured in the closure of the class such that it is truly private.

# Old-style module guidelines:

* Add `"use strict";` at the top of every old-style module (this is automatic for new-style modules).
* Name all entities exported by an old-style module:

Instead of 

```javascript
    return Widget.extend({
        // ...
    });
```

Prefer:

```javascript
    const MyWidget = Widget.extend({
        // ...
    });
    return MyWidget;
```
* Methods should be private if possible and those methods' names should begin with an underscore. They should never be called from another object.

* Never read an attribute of an attribute on something that you have a reference.
  So, this is not good:

```javascript
    this.myObject.propA.propB
```

# Legacy widgets guideline

* Avoid using legacy widgets in new code whenever possible.

* Never use a reference to the parent widget

* Avoid using the 'include' functionality: extending a class is fine and does not cause issue, including a class is much more fragile, and may not work.

* For the widgets, here is how the various attributes/functions should be ordered:

  1. All static attributes, such as `template`, `events`, `custom_events`, ...

  2. All methods from the lifecycle of a widget, in this order: `init`, `willStart`, `start`, `destroy`

  3. If there are public methods, a section titled "Public", with an empty line before and after

  4. All public methods, camelcased, in alphabetic order

  5. If there are private methods, a section titled "Private", with an empty line before and after

  6. All private methods, camelcased and prefixed with `_`, in alphabetic order

  7. If there are event handlers, a section titled "Handlers", with an empty line before and after

  8. All handlers, camelcased and prefixed with `_on`, in alphabetic order

  9. If there are static methods, they should be in a section titled "Static". All static methods are considered public, camelcased with no `_`.

* For the event handlers defined by the key `event` or `custom_events`, do not inline the function. Always add a string name, and add the definition in the handler section

* Use `this.$(...)` instead of `this.$el.find(...)`
