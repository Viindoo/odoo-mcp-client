<!-- SSOT snippet. Referenced by forward-port agents when handling new modules.
     Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/fp-installable-false.md. -->

# Forward-Port: New Module (installable=False Rule)

When a module appears for the first time on source repo (does not yet exist on target repo)
during forward-port, apply this rule in the module's `__manifest__.py` when it lands on
the target side. Do NOT upgrade the module content itself during forward-port - upgrades
happen at their appropriate time later.

## Manifest flags - Immediate action on landing

### 1. Set `'installable': False`

Prevents accidental installation before the module is properly integrated into the target
stack. The module will remain dormant until explicitly enabled after integration validation.

### 2. Comment out `'auto_install': True` (if present)

Add note: `# TODO: Uncomment when upgrading module to production-ready status`

Reason: When `installable` is set back to `True` later, `auto_install: True` must not
auto-install the module before you intend it. Comment it out now; both flags (`installable`
and `auto_install`) open together during the actual upgrade phase.

### 3. Comment out `'application': True` (if present)

Add note: `# TODO: Uncomment when upgrading module to production-ready status`

Reason: An incomplete module should not appear as a standalone app in the app store or top
menu. Comment it out now; both flags open together during upgrade.

## Code quality - Minimal fix only

If the new module's code violates lint / ESLint / Prettier rules:
- Fix ONLY to unblock the repo (reach green CI).
- Do NOT refactor or upgrade module content.
- Reason: forward-port carries intent and behavior, not a code upgrade opportunity. Nesting
  an upgrade inside forward-port conflates two separate decisions and masks which commit
  caused which change.

## Checklist for adapter (Phase 4c verification)

- [ ] `'installable': False` is set
- [ ] `'auto_install': True` is commented with TODO note
- [ ] `'application': True` is commented with TODO note
- [ ] Lint is green; no refactoring beyond lint fix
- [ ] All three flags (`installable`, `auto_install`, `application`) will open synchronously
      when module is truly ready for production

## When these flags re-open

All three commented flags re-open together during the actual module upgrade phase:
- Product owner confirms the module is integration-tested and stable on target.
- A separate, subsequent commit/PR upgrades: `installable: True` and uncomments the two
  conditional flags.
- This separation keeps forward-port commits focused on intent/behavior, upgrade commits
  focused on production-readiness.

## Related

- [[fp-merge-absorption]]: Merge-commit contract for all forward-port absorption work.
