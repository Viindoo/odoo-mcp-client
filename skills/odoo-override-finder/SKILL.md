# odoo-override-finder

**Persona:** Developer
**Triggers:** find override point for method X, where to hook into sale order confirmation, best place to extend partner creation, điểm override cho method X, override method Y ở module nào
**Tools used:** `find_override_point`, `resolve_method`, `suggest_pattern`

## Instructions

This skill helps developers identify the correct place and pattern to override or extend Odoo behavior. It prevents the common mistakes of overriding at the wrong level (e.g., bypassing the ORM by patching internal methods) or using deprecated override conventions.

Call `find_override_point` first to get the canonical override location for the target method or behavior. Then call `resolve_method` to retrieve the full override chain, showing all existing modules that already extend this method. Finally, call `suggest_pattern` to recommend the appropriate Odoo override pattern (e.g., `_action_confirm` super() chain vs. onchange vs. compute field).

Present a concrete code snippet template in the output, pre-filled with the correct class name, method signature, and `super()` call. Include a compatibility note indicating which Odoo versions this override point is stable in. If the method has existing overrides in the chain, warn the developer about potential conflicts.

## Output format

## Override Point: `<method_name>` in `<model_name>`

**Recommended override location:** `<module>/<file>.py` line ~<N>
**Pattern:** <override pattern name>
**Odoo version stability:** <version range>

### Code template
```python
<code snippet>
```

### Existing overrides in chain
| Module | File | Notes |
|--------|------|-------|
| ...    | ...  | ...   |

### Compatibility notes
<1–2 sentences>

## Example invocation

User: "where to hook into sale order confirmation to add custom validation"
Expected output: Recommended override of `_action_confirm` in `sale.order`, a code template with super() chain, and a list of modules that already override this method with conflict warnings if present.
