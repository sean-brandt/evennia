"""
Spawner

The spawner takes input files containing object definitions in
dictionary forms. These use a prototype architecture to define
unique objects without having to make a Typeclass for each.

The main function is `spawn(*prototype)`, where the `prototype`
is a dictionary like this:

```python
GOBLIN = {
 "typeclass": "types.objects.Monster",
 "key": "goblin grunt",
 "health": lambda: randint(20,30),
 "resists": ["cold", "poison"],
 "attacks": ["fists"],
 "weaknesses": ["fire", "light"]
 "tags": ["mob", "evil", ('greenskin','mob')]
 "args": [("weapon", "sword")]
 }
```

Possible keywords are:
    prototype - string parent prototype
    key - string, the main object identifier
    typeclass - string, if not set, will use `settings.BASE_OBJECT_TYPECLASS`
    location - this should be a valid object or #dbref
    home - valid object or #dbref
    destination - only valid for exits (object or dbref)

    permissions - string or list of permission strings
    locks - a lock-string
    aliases - string or list of strings
    exec - this is a string of python code to execute or a list of such codes.
        This can be used e.g. to trigger custom handlers on the object. The
        execution namespace contains 'evennia' for the library and 'obj'
    tags - string or list of strings or tuples `(tagstr, category)`. Plain
        strings will be result in tags with no category (default tags).
    attrs - tuple or list of tuples of Attributes to add. This form allows
    more complex Attributes to be set. Tuples at least specify `(key, value)`
        but can also specify up to `(key, value, category, lockstring)`. If
        you want to specify a lockstring but not a category, set the category
        to `None`.
    ndb_<name> - value of a nattribute (ndb_ is stripped)
    other - any other name is interpreted as the key of an Attribute with
        its value. Such Attributes have no categories.

Each value can also be a callable that takes no arguments. It should
return the value to enter into the field and will be called every time
the prototype is used to spawn an object. Note, if you want to store
a callable in an Attribute, embed it in a tuple to the `args` keyword.

By specifying the "prototype" key, the prototype becomes a child of
that prototype, inheritng all prototype slots it does not explicitly
define itself, while overloading those that it does specify.

```python
GOBLIN_WIZARD = {
 "prototype": GOBLIN,
 "key": "goblin wizard",
 "spells": ["fire ball", "lighting bolt"]
 }

GOBLIN_ARCHER = {
 "prototype": GOBLIN,
 "key": "goblin archer",
 "attacks": ["short bow"]
}
```

One can also have multiple prototypes. These are inherited from the
left, with the ones further to the right taking precedence.

```python
ARCHWIZARD = {
 "attack": ["archwizard staff", "eye of doom"]

GOBLIN_ARCHWIZARD = {
 "key" : "goblin archwizard"
 "prototype": (GOBLIN_WIZARD, ARCHWIZARD),
}
```

The *goblin archwizard* will have some different attacks, but will
otherwise have the same spells as a *goblin wizard* who in turn shares
many traits with a normal *goblin*.

"""
from __future__ import print_function

import copy
from django.conf import settings
from random import randint
import evennia
from evennia.objects.models import ObjectDB
from evennia.utils.utils import make_iter, all_from_module, dbid_to_obj

_CREATE_OBJECT_KWARGS = ("key", "location", "home", "destination")


def _handle_dbref(inp):
    return dbid_to_obj(inp, ObjectDB)


def _validate_prototype(key, prototype, protparents, visited):
    """
    Run validation on a prototype, checking for inifinite regress.

    """
    assert isinstance(prototype, dict)
    if id(prototype) in visited:
        raise RuntimeError("%s has infinite nesting of prototypes." % key or prototype)
    visited.append(id(prototype))
    protstrings = prototype.get("prototype")
    if protstrings:
        for protstring in make_iter(protstrings):
            if key is not None and protstring == key:
                raise RuntimeError("%s tries to prototype itself." % key or prototype)
            protparent = protparents.get(protstring)
            if not protparent:
                raise RuntimeError("%s's prototype '%s' was not found." % (key or prototype, protstring))
            _validate_prototype(protstring, protparent, protparents, visited)


def _get_prototype(dic, prot, protparents):
    """
    Recursively traverse a prototype dictionary, including multiple
    inheritance. Use _validate_prototype before this, we don't check
    for infinite recursion here.

    """
    if "prototype" in dic:
        # move backwards through the inheritance
        for prototype in make_iter(dic["prototype"]):
            # Build the prot dictionary in reverse order, overloading
            new_prot = _get_prototype(protparents.get(prototype, {}), prot, protparents)
            prot.update(new_prot)
    prot.update(dic)
    prot.pop("prototype", None)  # we don't need this anymore
    return prot


def _batch_create_object(*objparams):
    """
    This is a cut-down version of the create_object() function,
    optimized for speed. It does NOT check and convert various input
    so make sure the spawned Typeclass works before using this!

    Args:
        objsparams (tuple): Parameters for the respective creation/add
            handlers in the following order:
                - `create_kwargs` (dict): For use as new_obj = `ObjectDB(**create_kwargs)`.
                - `permissions` (str): Permission string used with `new_obj.batch_add(permission)`.
                - `lockstring` (str): Lockstring used with `new_obj.locks.add(lockstring)`.
                - `aliases` (list): A list of alias strings for
                    adding with `new_object.aliases.batch_add(*aliases)`.
                - `nattributes` (list): list of tuples `(key, value)` to be loop-added to
                    add with `new_obj.nattributes.add(*tuple)`.
                - `attributes` (list): list of tuples `(key, value[,category[,lockstring]])` for
                    adding with `new_obj.attributes.batch_add(*attributes)`.
                - `tags` (list): list of tuples `(key, category)` for adding
                    with `new_obj.tags.batch_add(*tags)`.
                - `execs` (list): Code strings to execute together with the creation
                    of each object. They will be executed with `evennia` and `obj`
                        (the newly created object) available in the namespace. Execution
                        will happend after all other properties have been assigned and
                        is intended for calling custom handlers etc.
            for the respective creation/add handlers in the following
            order: (create_kwargs, permissions, locks, aliases, nattributes,
            attributes, tags, execs)

    Returns:
        objects (list): A list of created objects

    Notes:
        The `exec` list will execute arbitrary python code so don't allow this to be availble to
        unprivileged users!

    """

    # bulk create all objects in one go

    # unfortunately this doesn't work since bulk_create doesn't creates pks;
    # the result would be duplicate objects at the next stage, so we comment
    # it out for now:
    #  dbobjs = _ObjectDB.objects.bulk_create(dbobjs)

    dbobjs = [ObjectDB(**objparam[0]) for objparam in objparams]
    objs = []
    for iobj, obj in enumerate(dbobjs):
        # call all setup hooks on each object
        objparam = objparams[iobj]
        # setup
        obj._createdict = {"permissions": make_iter(objparam[1]),
                           "locks": objparam[2],
                           "aliases": make_iter(objparam[3]),
                           "nattributes": objparam[4],
                           "attributes": objparam[5],
                           "tags": make_iter(objparam[6])}
        # this triggers all hooks
        obj.save()
        # run eventual extra code
        for code in objparam[7]:
            if code:
                exec(code, {}, {"evennia": evennia, "obj": obj})
        objs.append(obj)
    return objs


def spawn(*prototypes, **kwargs):
    """
    Spawn a number of prototyped objects.

    Args:
        prototypes (dict): Each argument should be a prototype
            dictionary.
    Kwargs:
        prototype_modules (str or list): A python-path to a prototype
            module, or a list of such paths. These will be used to build
            the global protparents dictionary accessible by the input
            prototypes. If not given, it will instead look for modules
            defined by settings.PROTOTYPE_MODULES.
        prototype_parents (dict): A dictionary holding a custom
            prototype-parent dictionary. Will overload same-named
            prototypes from prototype_modules.
        return_prototypes (bool): Only return a list of the
            prototype-parents (no object creation happens)

    """

    protparents = {}
    protmodules = make_iter(kwargs.get("prototype_modules", []))
    if not protmodules and hasattr(settings, "PROTOTYPE_MODULES"):
        protmodules = make_iter(settings.PROTOTYPE_MODULES)
    for prototype_module in protmodules:
        protparents.update(dict((key, val) for key, val in
                                all_from_module(prototype_module).items() if isinstance(val, dict)))
    # overload module's protparents with specifically given protparents
    protparents.update(kwargs.get("prototype_parents", {}))
    for key, prototype in protparents.items():
        _validate_prototype(key, prototype, protparents, [])

    if "return_prototypes" in kwargs:
        # only return the parents
        return copy.deepcopy(protparents)

    objsparams = []
    for prototype in prototypes:

        _validate_prototype(None, prototype, protparents, [])
        prot = _get_prototype(prototype, {}, protparents)
        if not prot:
            continue

        # extract the keyword args we need to create the object itself. If we get a callable,
        # call that to get the value (don't catch errors)
        create_kwargs = {}
        keyval = prot.pop("key", "Spawned Object %06i" % randint(1, 100000))
        create_kwargs["db_key"] = keyval() if callable(keyval) else keyval

        locval = prot.pop("location", None)
        create_kwargs["db_location"] = locval() if callable(locval) else _handle_dbref(locval)

        homval = prot.pop("home", settings.DEFAULT_HOME)
        create_kwargs["db_home"] = homval() if callable(homval) else _handle_dbref(homval)

        destval = prot.pop("destination", None)
        create_kwargs["db_destination"] = destval() if callable(destval) else _handle_dbref(destval)

        typval = prot.pop("typeclass", settings.BASE_OBJECT_TYPECLASS)
        create_kwargs["db_typeclass_path"] = typval() if callable(typval) else typval

        # extract calls to handlers
        permval = prot.pop("permissions", [])
        permission_string = permval() if callable(permval) else permval
        lockval = prot.pop("locks", "")
        lock_string = lockval() if callable(lockval) else lockval
        aliasval = prot.pop("aliases", "")
        alias_string = aliasval() if callable(aliasval) else aliasval
        tagval = prot.pop("tags", [])
        tags = tagval() if callable(tagval) else tagval
        attrval = prot.pop("attrs", [])
        attributes = attrval() if callable(tagval) else attrval

        exval = prot.pop("exec", "")
        execs = make_iter(exval() if callable(exval) else exval)

        # extract ndb assignments
        nattributes = dict((key.split("_", 1)[1], value() if callable(value) else value)
                           for key, value in prot.items() if key.startswith("ndb_"))

        # the rest are attributes
        simple_attributes = [(key, value()) if callable(value) else (key, value)
                             for key, value in prot.items() if not key.startswith("ndb_")]
        attributes = attributes + simple_attributes
        attributes = [tup for tup in attributes if not tup[0] in _CREATE_OBJECT_KWARGS]

        # pack for call into _batch_create_object
        objsparams.append((create_kwargs, permission_string, lock_string,
                           alias_string, nattributes, attributes, tags, execs))

    return _batch_create_object(*objsparams)


if __name__ == "__main__":
    # testing

    protparents = {
        "NOBODY": {},
        # "INFINITE" : {
        #     "prototype":"INFINITE"
        # },
        "GOBLIN": {
            "key": "goblin grunt",
            "health": lambda: randint(20, 30),
            "resists": ["cold", "poison"],
            "attacks": ["fists"],
            "weaknesses": ["fire", "light"]
        },
        "GOBLIN_WIZARD": {
            "prototype": "GOBLIN",
            "key": "goblin wizard",
            "spells": ["fire ball", "lighting bolt"]
        },
        "GOBLIN_ARCHER": {
            "prototype": "GOBLIN",
            "key": "goblin archer",
            "attacks": ["short bow"]
        },
        "ARCHWIZARD": {
            "attacks": ["archwizard staff"],
        },
        "GOBLIN_ARCHWIZARD": {
            "key": "goblin archwizard",
            "prototype": ("GOBLIN_WIZARD", "ARCHWIZARD")
        }
    }
    # test
    print([o.key for o in spawn(protparents["GOBLIN"],
                                protparents["GOBLIN_ARCHWIZARD"],
                                prototype_parents=protparents)])
