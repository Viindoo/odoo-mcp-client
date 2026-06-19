> Source: official Odoo 14.0 coding guidelines - https://raw.githubusercontent.com/odoo/documentation/14.0/content/contributing/development/coding_guidelines.rst

# Python

> **Warning:** Do not forget to read the Security Pitfalls (security.md) section as well to write secure code.

## PEP8 options

Using a linter can help show syntax and semantic warnings or errors. Odoo source code tries to respect Python standard, but some of them can be ignored.

- E501: line too long
- E301: expected 1 blank line, found 0
- E302: expected 2 blank lines, found 1

## Imports

The imports are ordered as

1. External libraries (one per line sorted and split in python stdlib)
2. Imports of `odoo`
3. Imports from Odoo modules (rarely, and only if necessary)

Inside these 3 groups, the imported lines are alphabetically sorted.

```python
# 1 : imports of python lib
import base64
import re
import time
from datetime import datetime
# 2 : imports of odoo
import odoo
from odoo import api, fields, models, _ # alphabetically ordered
from odoo.tools.safe_eval import safe_eval as eval
# 3 : imports from odoo addons
from odoo.addons.web.controllers.main import login_redirect
from odoo.addons.website.models.website import slug
```

## Idiomatics of Programming (Python)

- Always favor *readability* over *conciseness* or using the language features or idioms.
- Don't use `.clone()`

```python
# bad
new_dict = my_dict.clone()
new_list = old_list.clone()
# good
new_dict = dict(my_dict)
new_list = list(old_list)
```

- Python dictionary : creation and update

```python
# -- creation empty dict
my_dict = {}
my_dict2 = dict()

# -- creation with values
# bad
my_dict = {}
my_dict['foo'] = 3
my_dict['bar'] = 4
# good
my_dict = {'foo': 3, 'bar': 4}

# -- update dict
# bad
my_dict['foo'] = 3
my_dict['bar'] = 4
my_dict['baz'] = 5
# good
my_dict.update(foo=3, bar=4, baz=5)
my_dict = dict(my_dict, **my_dict2)
```

- Use meaningful variable/class/method names
- Useless variable : Temporary variables can make the code clearer by giving names to objects, but that doesn't mean you should create temporary variables all the time:

```python
# pointless
schema = kw['schema']
params = {'schema': schema}
# simpler
params = {'schema': kw['schema']}
```

- Multiple return points are OK, when they're simpler

```python
# a bit complex and with a redundant temp variable
def axes(self, axis):
    axes = []
    if type(axis) == type([]):
        axes.extend(axis)
    else:
        axes.append(axis)
    return axes

# clearer
def axes(self, axis):
    if type(axis) == type([]):
        return list(axis) # clone the axis
    else:
        return [axis] # single-element list
```

- Know your builtins : You should at least have a basic understanding of all the Python builtins (http://docs.python.org/library/functions.html)

```python
value = my_dict.get('key', None) # very very redundant
value = my_dict.get('key') # good
```

Also, `if 'key' in my_dict` and `if my_dict.get('key')` have very different meaning, be sure that you're using the right one.

- Learn list comprehensions : Use list comprehension, dict comprehension, and basic manipulation using `map`, `filter`, `sum`, ... They make the code easier to read.

```python
# not very good
cube = []
for i in res:
    cube.append((i['id'],i['name']))
# better
cube = [(i['id'], i['name']) for i in res]
```

- Collections are booleans too : In python, many objects have "boolean-ish" value when evaluated in a boolean context (such as an if). Among these are collections (lists, dicts, sets, ...) which are "falsy" when empty and "truthy" when containing items:

```python
bool([]) is False
bool([1]) is True
bool([False]) is True
```

So, you can write `if some_collection:` instead of `if len(some_collection):`.

- Iterate on iterables

```python
# creates a temporary list and looks bar
for key in my_dict.keys():
    "do something..."
# better
for key in my_dict:
    "do something..."
# accessing the key,value pair
for key, value in my_dict.items():
    "do something..."
```

- Use dict.setdefault

```python
# longer.. harder to read
values = {}
for element in iterable:
    if element not in values:
        values[element] = []
    values[element].append(other_value)

# better.. use dict.setdefault method
values = {}
for element in iterable:
    values.setdefault(element, []).append(other_value)
```

- As a good developer, document your code (docstring on methods, simple comments for tricky part of code)
- In additions to these guidelines, you may also find the following link interesting: http://python.net/~goodger/projects/pycon/2007/idiomatic/handout.html (a little bit outdated, but quite relevant)

## Programming in Odoo

- Avoid to create generators and decorators: only use the ones provided by the Odoo API.
- As in python, use `filtered`, `mapped`, `sorted`, ... methods to ease code reading and performance.

### Make your method work in batch

When adding a function, make sure it can process multiple records by iterating on self to treat each record.

```python
def my_method(self):
    for record in self:
        record.do_cool_stuff()
```

For performance issue, when developing a 'stat button' (for instance), do not perform a `search` or a `search_count` in a loop. It is recommended to use `read_group` method, to compute all value in only one request.

```python
def _compute_equipment_count(self):
    """ Count the number of equipment per category """
    equipment_data = self.env['hr.equipment'].read_group([('category_id', 'in', self.ids)], ['category_id'], ['category_id'])
    mapped_data = dict([(m['category_id'][0], m['category_id_count']) for m in equipment_data])
    for category in self:
        category.equipment_count = mapped_data.get(category.id, 0)
```

### Propagate the context

The context is a `frozendict` that cannot be modified. To call a method with a different context, the `with_context` method should be used :

```python
records.with_context(new_context).do_stuff() # all the context is replaced
records.with_context(**additionnal_context).do_other_stuff() # additionnal_context values override native context ones
```

> **Warning:** Passing parameter in context can have dangerous side-effects.
>
> Since the values are propagated automatically, some unexpected behavior may appear. Calling `create()` method of a model with *default_my_field* key in context will set the default value of *my_field* for the concerned model. But if during this creation, other objects (such as sale.order.line, on sale.order creation) having a field name *my_field* are created, their default value will be set too.

If you need to create a key context influencing the behavior of some object, choose a good name, and eventually prefix it by the name of the module to isolate its impact. A good example are the keys of `mail` module : *mail_create_nosubscribe*, *mail_notrack*, *mail_notify_user_signature*, ...

### Think extendable

Functions and methods should not contain too much logic: having a lot of small and simple methods is more advisable than having few large and complex methods. A good rule of thumb is to split a method as soon as it has more than one responsibility (see http://en.wikipedia.org/wiki/Single_responsibility_principle).

Hardcoding a business logic in a method should be avoided as it prevents to be easily extended by a submodule.

```python
# do not do this
# modifying the domain or criteria implies overriding whole method
def action(self):
    ...  # long method
    partners = self.env['res.partner'].search(complex_domain)
    emails = partners.filtered(lambda r: arbitrary_criteria).mapped('email')

# better but do not do this either
# modifying the logic forces to duplicate some parts of the code
def action(self):
    ...
    partners = self._get_partners()
    emails = partners._get_emails()

# better
# minimum override
def action(self):
    ...
    partners = self.env['res.partner'].search(self._get_partner_domain())
    emails = partners.filtered(lambda r: r._filter_partners()).mapped('email')
```

The above code is over extendable for the sake of example but the readability must be taken into account and a tradeoff must be made.

Also, name your functions accordingly: small and properly named functions are the starting point of readable/maintainable code and tighter documentation.

This recommendation is also relevant for classes, files, modules and packages. (See also http://en.wikipedia.org/wiki/Cyclomatic_complexity)

### Never commit the transaction

The Odoo framework is in charge of providing the transactional context for all RPC calls. The principle is that a new database cursor is opened at the beginning of each RPC call, and committed when the call has returned, just before transmitting the answer to the RPC client, approximately like this:

```python
def execute(self, db_name, uid, obj, method, *args, **kw):
    db, pool = pooler.get_db_and_pool(db_name)
    # create transaction cursor
    cr = db.cursor()
    try:
        res = pool.execute_cr(cr, uid, obj, method, *args, **kw)
        cr.commit() # all good, we commit
    except Exception:
        cr.rollback() # error, rollback everything atomically
        raise
    finally:
        cr.close() # always close cursor opened manually
    return res
```

If any error occurs during the execution of the RPC call, the transaction is rolled back atomically, preserving the state of the system.

Similarly, the system also provides a dedicated transaction during the execution of tests suites, so it can be rolled back or not depending on the server startup options.

The consequence is that if you manually call `cr.commit()` anywhere there is a very high chance that you will break the system in various ways, because you will cause partial commits, and thus partial and unclean rollbacks, causing among others:

1. inconsistent business data, usually data loss
2. workflow desynchronization, documents stuck permanently
3. tests that can't be rolled back cleanly, and will start polluting the database, and triggering error (this is true even if no error occurs during the transaction)

Here is the very simple rule:

> You should **NEVER** call `cr.commit()` yourself, **UNLESS** you have created your own database cursor explicitly! And the situations where you need to do that are exceptional!
>
> And by the way if you did create your own cursor, then you need to handle error cases and proper rollback, as well as properly close the cursor when you're done with it.

And contrary to popular belief, you do not even need to call `cr.commit()` in the following situations:

- in the `_auto_init()` method of an *models.Model* object: this is taken care of by the addons initialization method, or by the ORM transaction when creating custom models
- in reports: the `commit()` is handled by the framework too, so you can update the database even from within a report
- within *models.Transient* methods: these methods are called exactly like regular *models.Model* ones, within a transaction and with the corresponding `cr.commit()/rollback()` at the end
- etc. (see general rule above if you are in doubt!)

All `cr.commit()` calls outside of the server framework from now on must have an **explicit comment** explaining why they are absolutely necessary, why they are indeed correct, and why they do not break the transactions. Otherwise they can and will be removed !

### Use translation method correctly

Odoo uses a GetText-like method named "underscore" `_( )` to indicate that a static string used in the code needs to be translated at runtime using the language of the context. This pseudo-method is accessed within your code by importing as follows:

```python
from odoo import _
```

A few very important rules must be followed when using it, in order for it to work and to avoid filling the translations with useless junk.

Basically, this method should only be used for static strings written manually in the code, it will not work to translate field values, such as Product names, etc. This must be done instead using the translate flag on the corresponding field.

The method accepts optional positional or named parameter. The rule is very simple: calls to the underscore method should always be in the form `_('literal string')` and nothing else:

```python
# good: plain strings
error = _('This record is locked!')

# good: strings with formatting patterns included
error = _('Record %s cannot be modified!', record)

# ok too: multi-line literal strings
error = _("""This is a bad multiline example
             about record %s!""", record)
error = _('Record %s cannot be modified' \
          'after being validated!', record)

# bad: tries to translate after string formatting
#      (pay attention to brackets!)
# This does NOT work and messes up the translations!
error = _('Record %s cannot be modified!' % record)

# bad: formatting outside of translation
# This won't benefit from fallback mechanism in case of bad translation
error = _('Record %s cannot be modified!') % record

# bad: dynamic string, string concatenation, etc are forbidden!
# This does NOT work and messes up the translations!
error = _("'" + que_rec['question'] + "' \n")

# bad: field values are automatically translated by the framework
# This is useless and will not work the way you think:
error = _("Product %s is out of stock!") % _(product.name)
# and the following will of course not work as already explained:
error = _("Product %s is out of stock!" % product.name)

# Instead you can do the following and everything will be translated,
# including the product name if its field definition has the
# translate flag properly set:
error = _("Product %s is not available!", product.name)
```

Also, keep in mind that translators will have to work with the literal values that are passed to the underscore function, so please try to make them easy to understand and keep spurious characters and formatting to a minimum. Translators must be aware that formatting patterns such as `%s` or `%d`, newlines, etc. need to be preserved, but it's important to use these in a sensible and obvious manner:

```python
# Bad: makes the translations hard to work with
error = "'" + question + _("' \nPlease enter an integer value ")

# Ok (pay attention to position of the brackets too!)
error = _("Answer to question %s is not valid.\n" \
          "Please enter an integer value.", question)

# Better
error = _("Answer to question %(title)s is not valid.\n" \
          "Please enter an integer value.", title=question)
```

In general in Odoo, when manipulating strings, prefer `%` over `.format()` (when only one variable to replace in a string), and prefer `%(varname)` instead of position (when multiple variables have to be replaced). This makes the translation easier for the community translators.
