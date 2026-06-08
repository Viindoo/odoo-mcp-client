> Source: official Odoo 19.0 coding guidelines - https://raw.githubusercontent.com/odoo/documentation/19.0/content/contributing/development/coding_guidelines.rst

# CSS and SCSS

## Syntax and Formatting

SCSS:

```scss
.o_foo, .o_foo_bar, .o_baz {
   height: $o-statusbar-height;

   .o_qux {
      height: $o-statusbar-height * 0.5;
   }
}

.o_corge {
   background: $o-list-footer-bg-color;
}
```

CSS (compiled output):

```css
.o_foo, .o_foo_bar, .o_baz {
   height: 32px;
}

.o_foo .o_quux, .o_foo_bar .o_quux, .o_baz .o_qux {
   height: 16px;
}

.o_corge {
   background: #EAEAEA;
}
```

- four (4) space indents, no tabs;
- columns of max. 80 characters wide;
- opening brace (`{`): empty space after the last selector;
- closing brace (`}`): on its own new line;
- one line for each declaration;
- meaningful use of whitespace.

### Suggested Stylelint settings

```
"stylelint.config": {
    "rules": {
        // https://stylelint.io/user-guide/rules

        // Avoid errors
        "block-no-empty": true,
        "shorthand-property-no-redundant-values": true,
        "declaration-block-no-shorthand-property-overrides": true,

        // Stylistic conventions
        "indentation": 4,

        "function-comma-space-after": "always",
        "function-parentheses-space-inside": "never",
        "function-whitespace-after": "always",

        "unit-case": "lower",

        "value-list-comma-space-after": "always-single-line",

        "declaration-bang-space-after": "never",
        "declaration-bang-space-before": "always",
        "declaration-colon-space-after": "always",
        "declaration-colon-space-before": "never",

        "block-closing-brace-empty-line-before": "never",
        "block-opening-brace-space-before": "always",

        "selector-attribute-brackets-space-inside": "never",
        "selector-list-comma-space-after": "always-single-line",
        "selector-list-comma-space-before": "never-single-line",
    }
},
```

## Properties order

Order properties from the "outside" in, starting from `position` and ending with decorative rules (`font`, `filter`, etc.).

Scoped SCSS variables and CSS variables must be placed at the very top, followed by an empty line separating them from other declarations.

```
.o_element {
   $-inner-gap: $border-width + $legend-margin-bottom;

   --element-margin: 1rem;
   --element-size: 3rem;

   @include o-position-absolute(1rem);
   display: block;
   margin: var(--element-margin);
   width: calc(var(--element-size) + #{$-inner-gap});
   border: 0;
   padding: 1rem;
   background: blue;
   font-size: 1rem;
   filter: blur(2px);
}
```

## Naming Conventions

Naming conventions in CSS are incredibly useful in making your code more strict, transparent and informative.

Avoid `id` selectors, and prefix your classes with `o_<module_name>`, where `<module_name>` is the technical name of the module (`sale`, `im_chat`, ...) or the main route reserved by the module (for website modules mainly, i.e. : `o_forum` for the `website_forum` module).

The only exception for this rule is the webclient: it simply uses the `o_` prefix.

Avoid creating hyper-specific classes and variable names. When naming nested elements, opt for the "Grandchild" approach.

Don't

```html
<div class="o_element_wrapper">
   <div class="o_element_wrapper_entries">
      <span class="o_element_wrapper_entries_entry">
         <a class="o_element_wrapper_entries_entry_link">Entry</a>
      </span>
   </div>
</div>
```

Do

```html
<div class="o_element_wrapper">
   <div class="o_element_entries">
      <span class="o_element_entry">
         <a class="o_element_link">Entry</a>
      </span>
   </div>
</div>
```

Besides being more compact, this approach eases maintenance because it limits the need of renaming when changes occur at the DOM.

### SCSS Variables

Our standard convention is `$o-[root]-[element]-[property]-[modifier]`, with:

* `$o-`
    The prefix.
* `[root]`
    Either the component **or** the module name (components take priority).
* `[element]`
    An optional identifier for inner elements.
* `[property]`
    The property/behavior defined by the variable.
* `[modifier]`
    An optional modifier.

```scss
$o-block-color: value;
$o-block-title-color: value;
$o-block-title-color-hover: value;
```

### SCSS Variables (scoped)

These variables are declared within blocks and are not accessible from the outside. Our standard convention is `$-[variable name]`.

```scss
.o_element {
   $-inner-gap: compute-something;

   margin-right: $-inner-gap;

   .o_element_child {
      margin-right: $-inner-gap * 0.5;
   }
}
```

See also: [Variables scope on the SASS Documentation](https://sass-lang.com/documentation/variables#scope)

### SCSS Mixins and Functions

Our standard convention is `o-[name]`. Use descriptive names. When naming functions, use verbs in the imperative form (e.g.: `get`, `make`, `apply`...).

Name optional arguments in the scoped variables form, so `$-[argument]`.

```scss
@mixin o-avatar($-size: 1.5em, $-radius: 100%) {
   width: $-size;
   height: $-size;
   border-radius: $-radius;
}

@function o-invert-color($-color, $-amount: 100%) {
   $-inverse: change-color($-color, $-hue: hue($-color) + 180);

   @return mix($-inverse, $-color, $-amount);
}
```

See also:
- [Mixins on the SASS Documentation](https://sass-lang.com/documentation/at-rules/mixin)
- [Functions on the SASS Documentation](https://sass-lang.com/documentation/at-rules/function)

### CSS Variables

In Odoo, the use of CSS variables is strictly DOM-related. Use them to **contextually** adapt the design and layout.

Our standard convention is BEM, so `--[root]__[element]-[property]--[modifier]`, with:

* `[root]`
    Either the component **or** the module name (components take priority).
* `[element]`
    An optional identifier for inner elements.
* `[property]`
    The property/behavior defined by the variable.
* `[modifier]`
    An optional modifier.

```scss
.o_kanban_record {
   --KanbanRecord-width: value;
   --KanbanRecord__picture-border: value;
   --KanbanRecord__picture-border--active: value;
}

// Adapt the component when rendered in another context.
.o_form_view {
   --KanbanRecord-width: another-value;
   --KanbanRecord__picture-border: another-value;
   --KanbanRecord__picture-border--active: another-value;
}
```

## Use of CSS Variables

In Odoo, the use of CSS variables is strictly DOM-related, meaning that are used to **contextually** adapt the design and layout rather than to manage the global design-system. These are typically used when a component's properties can vary in specific contexts or in other circumstances.

We define these properties inside the component's main block, providing default fallbacks.

`my_component.scss`:

```scss
.o_MyComponent {
   color: var(--MyComponent-color, #313131);
}
```

`my_dashboard.scss`:

```scss
.o_MyDashboard {
   // Adapt the component in this context only
   --MyComponent-color: #017e84;
}
```

See also: [CSS variables on MDN web docs](https://developer.mozilla.org/en-US/docs/Web/CSS/Using_CSS_custom_properties)

### CSS and SCSS Variables

Despite being apparently similar, `CSS` and `SCSS` variables behave very differently. The main difference is that, while `SCSS` variables are **imperative** and compiled away, `CSS` variables are **declarative** and included in the final output.

See also: [CSS/SCSS variables difference on the SASS Documentation](https://sass-lang.com/documentation/variables)

In Odoo, we take the best of both worlds: using the `SCSS` variables to define the design-system while opting for the `CSS` ones when it comes to contextual adaptations.

The implementation of the previous example should be improved by adding SCSS variables in order to gain control at the top-level and ensure consistency with other components.

`secondary_variables.scss`:

```scss
$o-component-color: $o-main-text-color;
$o-dashboard-color: $o-info;
// [...]
```

`component.scss`:

```
.o_component {
   color: var(--MyComponent-color, #{$o-component-color});
}
```

`dashboard.scss`:

```
.o_dashboard {
   --MyComponent-color: #{$o-dashboard-color};
}
```

### The `:root` pseudo-class

Defining CSS variables on the `:root` pseudo-class is a technique we normally **don't use** in Odoo's UI. The practice is commonly used to access and modify CSS variables globally. We perform this using SCSS instead.

Exceptions to this rule should be fairly apparent, such as templates shared across bundles that require a certain level of contextual awareness in order to be rendered properly.
