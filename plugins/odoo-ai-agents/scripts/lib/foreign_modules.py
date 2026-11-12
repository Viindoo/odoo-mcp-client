"""foreign_modules.py - the installed modules that would write their text into the translation
catalog of an exported module (the rule behind instance_i18n_export's I18N_EXPORT_FOREIGN_MODULES).

Odoo exports a module's catalog from the database: every record the module owns (an external id in
its namespace) with the value the database holds NOW. A module that is installed alongside it and
is not in its dependency closure can change those values, whichever way the two are related:
  - it overrides a field's label or help, or adds fields to a model of the exported module: the
    one `ir.model.fields` row (per model and field) takes the LAST module's text, and the exported
    module's external id points at that row;
  - it adds fields to a mixin or parent model the exported module's models inherit, which the
    exported module's own reflection then registers under its namespace.
What a static read can say is which modules are installed outside the closure, not what each one
touches, so every one of them is foreign - a sibling, a bridge that depends on the exported module,
or a module of unrelated purpose alike.

A database that holds only the exported module and what it needs is the correct source, and it
holds exactly (the question is asked per exported module, and the other modules of the same call
are no exception: a module and one of its own dependencies are never both clean in one database,
since the dependent is foreign to the dependency - so a call is, in practice, one module per
database):
  - `base`, which every database holds;
  - the exported module's dependency closure (its `depends`, followed transitively);
  - the deployment's server-wide modules and their closure (installed on every database of that
    deployment, passed in as `always`);
  - on a series whose Odoo has no skip-auto-install option, the auto_install modules whose triggers
    are all present: Odoo installs them on any build there, so they are not a choice of the build.
    Where the option exists a build skips them, so an auto-installed bridge is foreign like any
    other - it is the polluting case, not an exemption.
Modules a closure module's post-install hook installs (they follow the company's country) are not
exempted: another build without that company setting avoids them.

Nothing is imported from Odoo: the caller hands `manifest_of(name)` (the manifest dict read as a
literal from the lease's addons path, or None when there is none).
"""
from __future__ import annotations

BASE = "base"


def dependency_closure(modules, manifest_of):
    """(the set of `modules` and everything they reach through `depends`, sorted list of the names
    whose manifest could not be read - their own dependencies are then unknown)."""
    seen, unread, todo = set(), [], list(modules)
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        if name == BASE:
            continue
        manifest = manifest_of(name)
        if manifest is None:
            unread.append(name)
            continue
        todo.extend(str(dep) for dep in manifest.get("depends") or [])
    return seen, sorted(unread)


def auto_install_triggers(manifest):
    """The modules whose presence installs this one by itself (manifest `auto_install`: True = all
    its `depends`, a list = those); an empty set when it never installs by itself."""
    value = manifest.get("auto_install") if manifest else None
    if isinstance(value, (list, tuple, set, frozenset)):
        return {str(v) for v in value}
    if value:
        return {str(dep) for dep in manifest.get("depends") or []}
    return set()


def _auto_installed(candidates, present, manifest_of):
    """The `candidates` Odoo installs by itself once `present` is installed: auto_install modules
    whose triggers are all present or themselves auto-installed (a fixpoint)."""
    found, pending = set(), set(candidates)
    changed = True
    while changed:
        changed = False
        for name in sorted(pending):
            triggers = auto_install_triggers(manifest_of(name))
            if triggers and triggers <= present | found:
                found.add(name)
                pending.discard(name)
                changed = True
    return found


def foreign_modules(exported, installed, manifest_of, always=(), skip_auto_install=True):
    """(foreign, unjudged): `foreign` = {exported module: sorted installed modules foreign to it},
    only for exported modules with any; `unjudged` = the exported modules whose verdict needs a
    manifest that could not be read, of a module the database holds (they are left out of
    `foreign`: a verdict is never guessed).
    `installed` = every module the database holds loaded; `always` = the deployment's server-wide
    modules; `skip_auto_install` = whether the series' Odoo can be told not to auto-install."""
    installed = set(installed)
    shared, shared_unread = dependency_closure([BASE] + list(always), manifest_of)
    foreign, unjudged = {}, []
    for module in exported:
        closure, unread = dependency_closure([module], manifest_of)
        # A module the database does not hold has no dependencies in it to account for.
        if installed.intersection(unread) or installed.intersection(shared_unread):
            unjudged.append(module)
            continue
        allowed = closure | shared
        outside = installed - allowed
        if not skip_auto_install:
            outside -= _auto_installed(outside, allowed, manifest_of)
        if outside:
            foreign[module] = sorted(outside)
    return foreign, unjudged
