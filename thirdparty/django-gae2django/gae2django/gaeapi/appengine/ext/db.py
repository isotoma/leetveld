import base64
import binascii
import cPickle
import logging
import os
import random
import re
import time
import types

from django.contrib.auth.models import User
from django.contrib.contenttypes import generic
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import manager
from django.db.models.fields.related import (
    ReverseSingleRelatedObjectDescriptor as RSROD)
from django.db.models.query import QuerySet
from django.db.models.query_utils import Q
from django.db.models.signals import post_init
from django.db import transaction
from django.utils.hashcompat import md5_constructor

from gae2django.middleware import get_current_user
from gae2django.utils import CallableString

# Use the system (hardware-based) random number generator if it exists.
# Taken from django.contrib.sessions.backends.base
if hasattr(random, 'SystemRandom'):
    randrange = random.SystemRandom().randrange
else:
    randrange = random.randrange
MAX_SESSION_KEY = 18446744073709551616L     # 2 << 63


class Query(QuerySet):

    def __init__(self, *args, **kwds):
        super(Query, self).__init__(*args, **kwds)
        self._listprop_filter = None

    def filter(self, *args, **kwds):
        if kwds:
            return super(Query, self).filter(*args, **kwds)
        property_operator, value = args
        if isinstance(value, basestring):
            value = u'%s' % value
            value = value.replace("'", "''")
        elif isinstance(value, Key):
            value = value.obj
        prop, op = property_operator.split(' ', 1)
        # TODO(andi): See GqlQuery. Refactor query building.
        if op.lower() in ('=', 'is'):
            self.query.add_q(Q(**{prop: value}))
        elif op == '>':
            self.query.add_q(Q(**{'%s__gt' % prop: value}))
        elif op == '<':
            self.query.add_q(Q(**{'%s__lt' % prop: value}))
        elif op == '>=':
            self.query.add_q(Q(**{'%s__gte' % prop: value}))
        elif op == '<=':
            self.query.add_q(Q(**{'%s__lte' % prop: value}))
        else:
            where = '%s %r' % (property_operator, value)
            self.query.add_extra(None, None, [where], None, None, None)
        return self

    def _filter(self, *args, **kwds):
        return super(Query, self).filter(*args, **kwds)

    def order(self, prop):
        self.query.add_ordering(prop)

    def get(self, *args, **kwds):
        if kwds:
            return super(Query, self).get(*args, **kwds)
        results = list(self)
        if results:
            return results[0]
        return None

    def ancestor(self, ancestor):
        pattern = '@@'.join(str(x.key()) for x in ancestor.get_ancestry())
        # TODO(andi): __startswith would be better, see issue21
        self.query.add_q(Q(gae_ancestry__endswith='@%s@' % pattern))

    def fetch(self, limit, offset=0):
        return list(self)[offset:limit]

    def iterator(self):
        """Handles ListProperty filters."""
        for obj in super(Query, self).iterator():
            if self._listprop_filter is not None:
                matched = True
                for kwd, item in self._listprop_filter:
                    if item not in getattr(obj, kwd):
                        matched = False
                        break
                if matched:
                    yield obj
            else:
                yield obj


class BaseManager(manager.Manager):

    def __iter__(self):
        return self.iterator()

    def _filter(self, *args, **kwds):
        return self.get_query_set()._filter(*args, **kwds)

    def count(self, limit=None):
        return super(BaseManager, self).count()

    def order(self, *args, **kwds):
        return super(BaseManager, self).order_by(*args, **kwds)

    def get_query_set(self):
        return Query(self.model)


def _adjust_keywords(kwds):
    required = kwds.get('required', False)
    kwds['null'] = not required
    kwds['blank'] = not required
    if 'required' in kwds:
        del kwds['required']
    if 'choices' in kwds:
        kwds['choices'] = [(a, a) for a in kwds['choices']]
    return kwds


class StringProperty(models.CharField):

    def __init__(self, *args, **kwds):
        kwds = _adjust_keywords(kwds)
        kwds['max_length'] = 500
        super(StringProperty, self).__init__(*args, **kwds)


class TextProperty(models.TextField):

    def __init__(self, *args, **kwds):
        kwds = _adjust_keywords(kwds)
        super(TextProperty, self).__init__(*args, **kwds)


class BooleanProperty(models.NullBooleanField):

    def __init__(self, *args, **kwds):
        kwds = _adjust_keywords(kwds)
        super(BooleanProperty, self).__init__(*args, **kwds)


class UserProperty(models.ForeignKey):

    def __init__(self, *args, **kwds):
        kwds = _adjust_keywords(kwds)
        self._auto_current_user_add = False
        if 'auto_current_user_add' in kwds:
            self._auto_current_user_add = True
            del kwds['auto_current_user_add']
        super(UserProperty, self).__init__(User, *args, **kwds)

    def get_default(self):
        if self._auto_current_user_add:
            user = get_current_user()
            if user is not None:
                return user.id
            else:
                return None
            return get_current_user()
        return super(UserProperty, self).get_default()

def patch_user_model(sender, **kwds):
    if sender != User:
        return
    if not 'instance' in kwds:  # just to go for sure, shouldn't happen
        return
    instance = kwds['instance']
    if not isinstance(instance.email, CallableString):
        instance.email = CallableString(instance.email)
    if not hasattr(instance, 'nickname'):
        nickname = CallableString()
        # TODO(andi): Commented since it's a performance killer.
        #  All tests pass and at least Rietveld seems to run fine.
        #  I'll leave it in the sources in case it comes up again...
#        try:
#            profile = instance.get_profile()
#            if hasattr(profile, 'nickname'):
#                nickname = CallableString(profile.nickname)
#        except:
#            pass
        instance.nickname = nickname

post_init.connect(patch_user_model)


class DateTimeProperty(models.DateTimeField):

    def __init__(self, *args, **kwds):
        kwds = _adjust_keywords(kwds)
        super(DateTimeProperty, self).__init__(*args, **kwds)


class ListProperty(models.TextField):

    __metaclass__ = models.SubfieldBase

    def __init__(self, type_, *args, **kwds):
        kwds = _adjust_keywords(kwds)
        super(models.TextField, self).__init__()

    def get_db_prep_value(self, value, connection=None, prepared=False):
        return base64.encodestring(cPickle.dumps(value))

    def to_python(self, value):
        if type(value) in [types.ListType, types.TupleType]:
            return value
        if value is None:
            return []
        try:
            return cPickle.loads(base64.decodestring(value))
        except EOFError:
            return []



Email = str
Link = str
Text = unicode

class Blob(str):
    pass

class G2DReverseSingleRelatedObjectDescriptor(RSROD):

    def get_value_for_datastore(self, model_instance):
        return getattr(model_instance, self.__id_attr_name())

    def __id_attr_name(self):
        return self._attr_name()

    def _attr_name(self):
        return "_%s" % self.field.name


class ReferenceProperty(models.ForeignKey):

    def __init__(self, other, *args, **kwds):
        kwds = _adjust_keywords(kwds)
        if 'collection_name' in kwds:
            kwds['related_name'] = kwds['collection_name']
            del kwds['collection_name']
        super(ReferenceProperty, self).__init__(other, *args, **kwds)

    def contribute_to_class(self, cls, name):
        # This is mainly a copy of the ForeignKey's contribute_to_class.
        # The only difference is that we use our custom
        # ReverseSingleRelatedObjectDescriptor that implements
        # get_value_for_datastore (see issue 1).
        super(ReferenceProperty, self).contribute_to_class(cls, name)
        setattr(cls, self.name, G2DReverseSingleRelatedObjectDescriptor(self))
        if isinstance(self.rel.to, basestring):
            target = self.rel.to
        else:
            target = self.rel.to._meta.db_table
        cls._meta.duplicate_targets[self.column] = (target, "o2m")

SelfReferenceProperty = ReferenceProperty


class BlobProperty(models.TextField):

    __metaclass__ = models.SubfieldBase

    def __init__(self, *args, **kwds):
        kwds = _adjust_keywords(kwds)
        super(BlobProperty, self).__init__(*args, **kwds)

    def get_db_prep_value(self, value, connection=None, prepared=False):
        if value is None:
            return value
        return base64.encodestring(value)

    def to_python(self, value):
        if value is None:
            return value
        if isinstance(value, Blob):
            return value
        elif isinstance(value, unicode):
            # For legacy data
            value = value.encode('utf-8')
        try:
            return Blob(base64.decodestring(value))
        except binascii.Error:
            # value is already decoded, or for legacy data it was
            # never encoded
            return Blob(value)


class LinkProperty(models.URLField):

    def __init__(self, *args, **kwds):
        kwds = _adjust_keywords(kwds)
        super(LinkProperty, self).__init__(*args, **kwds)


class EmailProperty(models.EmailField):

    def __init__(self, *args, **kwds):
        kwds = _adjust_keywords(kwds)
        super(EmailProperty, self).__init__(*args, **kwds)


class IntegerProperty(models.IntegerField):

    def __init__(self, *args, **kwds):
        kwds = _adjust_keywords(kwds)
        super(IntegerProperty, self).__init__(*args, **kwds)


class BaseModelMeta(models.base.ModelBase):

    def __new__(cls, name, bases, attrs):
        new_cls = super(BaseModelMeta, cls).__new__(cls, name, bases, attrs)
        new_cls.objects = BaseManager()
        new_cls.objects.model = new_cls
        new_cls._default_manager = new_cls.objects
        new_cls._reference_attrs = set()
        for name in set(attrs):
            value = attrs[name]
            if isinstance(value, (ReferenceProperty, SelfReferenceProperty)):
                new_cls._reference_attrs.add(name)
        return new_cls


class Model(models.Model):

    __metaclass__ = BaseModelMeta

    gae_key = models.CharField(max_length=64, blank=True, null=True,
                               unique=True)
    gae_parent_ctype = models.ForeignKey(ContentType,
                                         blank=True, null=True)
    gae_parent_id = models.PositiveIntegerField(blank=True, null=True)
    gae_ancestry = models.CharField(max_length=500, blank=True, null=True)
    parent = generic.GenericForeignKey('gae_parent_ctype',
                                       'gae_parent_id')

    class Meta:
        abstract = True

    def __init__(self, *args, **kwds):
        # keywords for GenericForeignKeys don't work with abstract classes:
        # http://code.djangoproject.com/ticket/8309
        if 'parent' in kwds:
            parent = kwds['parent']
            ctype = ContentType.objects.get_for_model(parent.__class__)
            kwds['gae_parent_ctype'] = ctype
            kwds['gae_parent_id'] = parent.id
            kwds['gae_ancestry'] = ''.join(['@%s@' % prnt.key()
                                            for prnt in parent.get_ancestry()])

            del kwds['parent']
        if 'key' in kwds:
            kwds['gae_key'] = kwds['key']
            del kwds['key']
        if 'key_name' in kwds:
            kwds['gae_key'] = kwds['key_name']
            del kwds['key_name']
        self._key = None
        super(Model, self).__init__(*args, **kwds)

    def __getattribute__(self, name):
        ref_attrs = super(Model, self).__getattribute__('_reference_attrs')
        if name.startswith('_') and name[1:] in ref_attrs:
            referenced = super(Model, self).__getattribute__(name[1:])
            if referenced is not None:
                return referenced.key()
            return None
        return super(Model, self).__getattribute__(name)

    @classmethod
    def get_or_insert(cls, key, **kwds):
        try:
            return cls.objects.get(gae_key=key)
        except cls.DoesNotExist:
            kwds['gae_key'] = key
            new = cls(**kwds)
            new.save()
            return new

    @classmethod
    def get_by_key_name(cls, keys, parent=None):
        single = False
        # if keys isn't a list then a single instance is returned
        if type(keys) not in [types.ListType, types.TupleType]:
            single = True
            keys = [keys]
        result = []
        for key in keys:
            try:
                kwds = {'gae_key': str(key)}
                if parent is not None:
                    kwds['gae_ancestry__icontains'] = str(parent.key())
                result.append(cls.objects.get(**kwds))
            except cls.DoesNotExist:
                result.append(None)
        if single and len(result) != 0:
            return result[0]
        elif single:
            return None
        else:
            return result

    @classmethod
    def get_by_id(cls, id_, parent=None):
        # Ignore parent, we've got an ID
        ret = []
        return_list = True
        if type(id_) not in (types.ListType, types.TupleType):
            id_ = [id_]
            return_list = False
        for i in id_:
            try:
                ret.append(cls.objects.get(id=i))
            except cls.DoesNotExist:
                ret.append(None)
        if len(id_) == 1 and not return_list:
            return ret[0]
        else:
            return ret

    @classmethod
    def kind(cls):
        # Return the table name here. It should be the expected output...
        return cls._meta.db_table

    @classmethod
    def all(cls):
        return cls.objects.all()

    @classmethod
    def properties(cls):
        props = {}
        [props.setdefault(field.name, field) for field in cls._meta.fields
         if not field.name.startswith('gae_')]
        return props

    def key(self):
        if self.id is None:
            raise NotSavedError()
        if self._key is None:
            self._key = Key('%s_%s' % (self.__class__.__name__, self.id))
            self._key._obj = self
        return self._key

    def is_saved(self):
        return self.id is not None

    def put(self):
        return self.save()

    def save(self):
        if not self.key:
            try:
                pid = os.getpid()
            except AttributeError:
                pid = 1
            self.key = md5_constructor("%s%s%s%s"
                                       % (randrange(0, MAX_SESSION_KEY),
                                          pid, time.time(),
                                          self.__name__)).hexdigest()
        super(Model, self).save()

    @classmethod
    def gql(cls, clause, *args, **kwds):
        from google.appengine.ext import db
        query = db.GqlQuery('SELECT * FROM %s %s' % (cls.__name__,
                                                     clause), *args, **kwds)
        query._real_cls = cls
        return query

    @classmethod
    def get(cls, keys):
        if type(keys) not in [types.ListType, types.TupleType]:
            keys = [keys]
        instances = [cls.get_by_key_name(key) for key in keys]
        if len(keys) == 1:
            return instances[0]
        else:
            return instances

    def parent_key(self):
        return self.parent.key()

    def get_ancestry(self):
        """Returns parent objects."""
        yield self
        parent = self.parent
        while parent:
            yield parent
            parent = parent.parent



from django import forms as djangoforms


class _QueryIterator(object):

    def __init__(self, results):
        self._results = results
        self._idx = -1

    def __iter__(self):
        return self

    def next(self):
        self._idx += 1
        if len(self._results) > self._idx:
            return self._results[self._idx]
        else:
            raise StopIteration


class GqlQuery(object):

    def __init__(self, sql, *args, **kwds):
        from gaeapi.appengine.ext import gql
        #print sql, args, kwds
        self._sql = sql
        self._gql = gql.GQL(sql)
        self._real_cls = None
        self._args = []
        self._kwds = {}
        if args or kwds:
            self.bind(*args, **kwds)
        self._cursor = None
        self._idx = -1
        self._results = None

    def __iter__(self):
        if self._results is None:
            self._execute()
        return _QueryIterator(self._results)

    def _resolve_arg(self, value):
        from gaeapi.appengine.ext import gql
        if isinstance(value, basestring):
            return self._kwds[value]
        elif isinstance(value, int):
            return self._args[value-1]
        elif isinstance(value, gql.Literal):
            return value.Get()
        else:
            raise Error('Unhandled args %s' % item)

    def _execute(self):
        from gaeapi.appengine.ext import gql
        if self._cursor:
            raise Error('Already executed.')
        # Make sql local just for traceback
        sql = self._sql
        from django.db import models
        # First, let's see if the class is explicitely given.
        # E.g. Model.gql('xxx') set's _real_cls.
        cls = self._real_cls
        if cls is None:
            for xcls in models.get_models():
                if (xcls.__name__ == self._gql._entity \
                    or xcls._meta.db_table in self._sql) \
                and not xcls.__module__.startswith('django.'):
                    cls = xcls
                    break
        if not cls:
            raise Error('Class not found.')
        q = cls.objects.all()
        q = q.select_related()
        #print '-'*10
        #print "xx", sql, self._args, self._kwds
        ancestor = None
        listprop_filter = []
        for key, value in self._gql.filters().items():
            #print key, value
            kwd, op = key
            if op == '=':
                if cls._meta.get_field(kwd).rel:
                    rel_cls = cls._meta.get_field(kwd).rel.to
                else:
                    rel_cls = None
                for xop, val in value:
                    # FIXME: Handle lists...
                    item = val[0]

                    if isinstance(item, gql.Literal):
                        #print 'Literal', item
                        item = item.Get()
                        #print '-->', item
                    elif isinstance(item, basestring):
                        #print 'Keyword', item
                        item = self._kwds[item]
                        #print '-->', item
                    elif isinstance(item, int):
                        #print 'Positional', item
                        item = self._args[item-1]
                        #print '-->', item
                    else:
                        raise Error('Unhandled args %s' % item)
#                    if rel_cls:
#                        # FIXME: Handle lists
#                        try:
#                            item = rel_cls.objects.get(id=item)
#                        except rel_cls.DoesNotExist:
#                            continue
                    if isinstance(cls._meta.get_field(kwd), ListProperty):
                        listprop_filter.append((kwd, item))
                        continue
                    if isinstance(kwd, unicode):
                        kwd = kwd.encode('ascii')
                    q = q._filter(**{kwd: item})
            elif op == 'is' and kwd == -1: # ANCESTOR
                if ancestor:
                    raise Error('Ancestor already defined: %s' % ancestor)
                item = value[0][1][0]
                if isinstance(item, basestring):
                    ancestor = self._kwds[item]
                elif isinstance(item, int):
                    ancestor = self._args[item-1]
                else:
                    raise Error('Unhandled args %s' % item)
                pattern = '@%s@' % ancestor.key()
                q = q._filter(**{'gae_ancestry__contains': pattern})
            elif op == '>':
                item = self._resolve_arg(value[0][1][0])
                q = q._filter(**{'%s__gt' % kwd: item})
            elif op == '<':
                item = self._resolve_arg(value[0][1][0])
                q = q._filter(**{'%s__lt' % kwd: item})
            elif op == '>=':
                item = self._resolve_arg(value[0][1][0])
                q = q._filter(**{'%s__gte' % kwd: item})
            elif op == '<=':
                item = self._resolve_arg(value[0][1][0])
                q = q._filter(**{'%s__lte' % kwd: item})
            else:
                raise Error('Unhandled operator %s' % op)
        orderings = []
        for field, direction in self._gql.orderings():
            if direction != 1:
                field = '-%s' % field
            orderings.append(field)
        if orderings:
            q = q.order_by(*orderings)
        if listprop_filter:
            q._listprop_filter = listprop_filter
        self._results = q

    def bind(self, *args, **kwds):
        self._kwds = kwds
        self._args = args
        self._results = None

    def fetch(self, limit, offset=0):
        if self._results is None:
            self._execute()
        return list(self._results[offset:offset+limit])

    def count(self, limit=None):
        if self._results is None:
            self._execute()
        idx = self._idx
        c = len(self._results)
        self._idx = idx
        return c

    def get(self):
        if self._results is None:
            self._execute()
        if self._results:
            return self._results.get()
        return None


class Key(object):

    def __init__(self, key_str):
        if not isinstance(key_str, basestring):
            raise BadArgumentError(('Key() expects a string; '
                                    'received %s (a %s)'
                                    % (key_str, type(key_str))))
        self._obj = None
        self._key_str = key_str

    def __str__(self):
        return self._key_str

    def __cmp__(self, other):
        return cmp(str(self), str(other))

    def __hash__(self):
        return hash(self.__str__())

    def _get_obj(self):
        if self._obj is None:
            self._init_obj()
        return self._obj

    def _set_obj(self, obj):
        self._obj = obj

    obj = property(fget=_get_obj, fset=_set_obj)

    @classmethod
    def _find_model_cls(cls, name):
        from django.db.models.loading import get_models
        model_cls = None
        for model in get_models():
            if model.__module__.startswith('django'):
                continue
            if model.__name__ == name:
                model_cls = model
                break
        assert model_cls is not None
        return model_cls

    def _init_obj(self):
        clsname, objid = self._key_str.rsplit('_', 1)
        model_cls = self._find_model_cls(clsname)
        return model_cls.objects.get(int(objid))

    @classmethod
    def from_path(cls, *args, **kwds):
        if kwds and tuple(kwds) != ('parent',):
            raise BadArgumentError('Excess keyword arguments %r' % kwds)
        if len(args)%2 != 0 or len(args) == 0:
            raise BadArgumentError(('A non-zero even number of positional '
                                    'arguments is required (kind, id or name, '
                                    'kind, id or name, ...); received %s'
                                    % repr(args)))
        cls_name = args[-2]
        key_name = args[-1]
        if isinstance(key_name, basestring) and not key_name.isdigit():
            model_cls = cls._find_model_cls(cls_name)
            obj = model_cls.objects.get(gae_key=key_name)
            key = obj.key()
        else:
            key = cls('%s_%s' % (cls_name, key_name), **kwds)
        return key

    def app(self):
        return self.obj._meta.app_label

    def kind(self):
        return self.obj.__class__.__name__

    def id(self):
        if self.name():
            return None
        return self.obj.id

    def name(self):
        return self.obj.gae_key

    def id_or_name(self):
        if self.name() is None:
            return self.id()
        return self.name()

    def has_id_or_name(self):
        # Always returns True as we've always have at least an id...
        return True

    def parent(self):
        return self.obj.parent.key()


# Errors


class Error(Exception):
    """db.Error"""


class BadArgumentError(Error):
    """A bad argument was given to a query method."""


class BadFilterError(Error):
    """A filter string in the query is invalid."""


class BadKeyError(Error):
    """The provided key string is not a valid key."""


class BadPropertyError(Error):
    """The property could not be created because its name is not a string."""


class BadQueryError(Error):
    """The query string is not a valid query."""


class BadRequestError(Error):
    """Request to the datastore service has one or more invalid properties."""


class BadValueError(Error):
    """Invalid value for the property type."""


class ConfigurationError(Error):
    """A property is not configured correctly."""


class DuplicatePropertyError(Error):
    """A model definition has more than one property with the same name."""


class InternalError(Error):
    """There was an error internal to the datastore service."""


class KindError(Error):
    """Model class that does not match the entity."""


class NotSavedError(Error):
    """Object is not saved."""


class PropertyError(Error):
    """The referenced model property does not exist on the data object."""


class ReservedWordError(Error):
    """A model defines a property whose name is disallowed."""


class Rollback(Error):
    """Indicates that a function in a transaction wants to roll back."""


class TransactionFailedError(Error):
    """The transaction or datastore operation could not be committed."""


class CapabilityDisabledError(Error):
    """Datastore functionality is not available."""


# Functions


def get(keys):
    raise NotImplementedError


def put(models):
    if type(models) not in [types.ListType, types.TupleType]:
        models = [models]
    keys = []
    for model in models:
        model.save()
        keys.append(model.key)
    if len(keys) > 1:
        return keys
    elif len(keys) == 1:
        return keys[0]
    return None


def delete(models):
    if type(models) not in [types.ListType, types.TupleType]:
        models = [models]
    for model in models:
        model.delete()


@transaction.commit_on_success
def run_in_transaction(func, *args, **kwds):
    return func(*args, **kwds)
