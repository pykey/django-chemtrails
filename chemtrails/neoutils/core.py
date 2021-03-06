# -*- coding: utf-8 -*-

import itertools
import operator
from functools import reduce

from django.db import models
from django.db.models import Manager
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ImproperlyConfigured, ValidationError, ObjectDoesNotExist

from neomodel import *
from chemtrails import settings
from chemtrails.utils import get_model_string, flatten


field_property_map = {
    models.ForeignKey: RelationshipTo,
    models.OneToOneField: RelationshipTo,
    models.ManyToManyField: RelationshipTo,
    models.ManyToOneRel: RelationshipTo,
    models.OneToOneRel: RelationshipTo,
    models.ManyToManyRel: RelationshipTo,

    models.AutoField: IntegerProperty,
    # models.BigAutoField: IntegerProperty,  # Breaks Django 1.9 compatibility
    models.BigIntegerField: IntegerProperty,
    models.BooleanField: BooleanProperty,
    models.CharField: StringProperty,
    models.CommaSeparatedIntegerField: ArrayProperty,
    models.DateField: DateProperty,
    models.DateTimeField: DateTimeProperty,
    models.DecimalField: FloatProperty,
    models.DurationField: StringProperty,
    models.EmailField: StringProperty,
    models.FilePathField: StringProperty,
    models.FileField: StringProperty,
    models.FloatField: FloatProperty,
    models.GenericIPAddressField: StringProperty,
    models.IntegerField: IntegerProperty,
    models.IPAddressField: StringProperty,
    models.NullBooleanField: BooleanProperty,
    models.PositiveIntegerField: IntegerProperty,
    models.PositiveSmallIntegerField: IntegerProperty,
    models.SlugField: StringProperty,
    models.SmallIntegerField: IntegerProperty,
    models.TextField: StringProperty,
    models.TimeField: IntegerProperty,
    models.URLField: StringProperty,
    models.UUIDField: StringProperty
}

# Caches to avoid infinity loops
__node_cache__ = {}
__meta_cache__ = {}


class Meta(type):
    """
    Meta class template.
    """
    model = None
    app_label = None

    def __new__(mcs, name, bases, attrs):
        cls = super(Meta, mcs).__new__(mcs, str(name), bases, attrs)
        return cls


class NodeBase(NodeMeta):
    """
    Base Meta class for ``StructuredNode`` which adds a model class.
    """
    def __new__(mcs, name, bases, attrs):
        cls = super(NodeBase, mcs).__new__(mcs, str(name), bases, attrs)

        if getattr(cls, 'Meta', None):
            meta = Meta('Meta', (Meta,), dict(cls.Meta.__dict__))

            # A little hack which helps us dynamically create ModelNode classes
            # where variables holding the model class is out of scope.
            if hasattr(cls, '__metaclass_model__') and not meta.model:
                meta.model = getattr(cls, '__metaclass_model__', None)
                delattr(cls, '__metaclass_model__')

            if not getattr(meta, 'model', None):
                raise ValueError('%s.Meta.model attribute cannot be None.' % name)

            if getattr(meta, 'app_label', None) is None:
                meta.app_label = meta.model._meta.app_label

            cls.add_to_class('Meta', meta)

        elif not getattr(cls, '__abstract_node__', None):
            raise ImproperlyConfigured('%s must implement a Meta class.' % name)

        return cls

    def add_to_class(cls, name, value):
        setattr(cls, name, value)


class ModelNodeMeta(NodeBase):
    """
    Meta class for ``ModelNode``.
    """
    def __new__(mcs, name, bases, attrs):
        cls = super(ModelNodeMeta, mcs).__new__(mcs, str(name), bases, attrs)

        # Set label for node
        cls.__label__ = '{object_name}Node'.format(object_name=cls.Meta.model._meta.object_name)

        # Add some default fields
        cls.type = StringProperty(default='ModelNode')
        cls.pk = cls.get_property_class_for_field(cls._pk_field.__class__)(unique_index=True)
        cls.app_label = StringProperty(default=cls.Meta.app_label)
        cls.model_name = StringProperty(default=cls.Meta.model._meta.model_name)

        forward_relations = cls.get_forward_relation_fields()
        reverse_relations = cls.get_reverse_relation_fields()

        # Add to cache before recursively looking up relationships.
        __node_cache__.update({cls.Meta.model: cls})

        for field in cls.Meta.model._meta.get_fields():

            # Add forward relations
            if field in forward_relations:
                relation = cls.get_related_node_property_for_field(field)
                cls.add_to_class(field.name, relation)

            # Add reverse relations
            elif field in reverse_relations:
                relation = cls.get_related_node_property_for_field(field)
                cls.add_to_class(field.related_name or '%s_set' % field.name, relation)

            # Add concrete fields
            else:
                if field is not cls._pk_field:
                    cls.add_to_class(field.name, cls.get_property_class_for_field(field.__class__)())

        # Recalculate definitions
        cls.__all_properties__ = tuple(cls.defined_properties(aliases=False, rels=False).items())
        cls.__all_aliases__ = tuple(cls.defined_properties(properties=False, rels=False).items())
        cls.__all_relationships__ = tuple(cls.defined_properties(aliases=False, properties=False).items())

        install_labels(cls, quiet=True, stdout=None)
        return cls


class ModelNodeMixinBase:
    """
    Base mixin class
    """
    @classproperty
    def _pk_field(cls):
        model = cls.Meta.model
        pk_field = reduce(operator.eq,
                          filter(lambda field: field.primary_key, model._meta.fields))
        return pk_field

    @classproperty
    def has_relations(cls):
        return len(cls.__all_relationships__) > 0

    @staticmethod
    def get_property_class_for_field(klass):
        """
        Returns the appropriate property class for field class.
        """
        if klass in field_property_map:
            return field_property_map[klass]
        raise NotImplementedError('Unsupported field. Field %s is currently not supported.' % klass.__name__)

    @staticmethod
    def get_relation_fields(model):
        """
        Get a list of fields on the model which represents relations.
        """
        return [
            field for field in model._meta.get_fields()
            if field.is_relation or field.one_to_one or (field.many_to_one and field.related_model)
        ]

    @classmethod
    def get_forward_relation_fields(cls):
        return [
            field for field in cls.Meta.model._meta.get_fields()
            if field.is_relation and (
                not field.auto_created or field.concrete
                or field.one_to_one
                or (field.many_to_one and field.related_model)
            )
        ]

    @classmethod
    def get_reverse_relation_fields(cls):
        return [
            field for field in cls.Meta.model._meta.get_fields()
            if field.auto_created and not field.concrete and (
                field.one_to_many
                or field.many_to_many
                or field.one_to_one
            )
        ]

    @classmethod
    def get_relationship_type(cls, field):
        """
        Get the relationship type for field. If ``settings.NAMED_RELATIONSHIPS``
        is True, pick the relationship type from the field. If not,
        use a pre-defined set of generic types.
        """
        generic_types = {
            Relationship: 'MUTUAL_RELATION',
            RelationshipTo: 'RELATES_TO',
            RelationshipFrom: 'RELATES_FROM'
        }
        if settings.NAMED_RELATIONSHIPS:
            return '{related_name}'.format(
                related_name=getattr(field, 'related_name', field.name) or field.name).upper()
        else:
            prop = cls.get_property_class_for_field(field.__class__)
            return generic_types[prop]

    @classmethod
    def get_related_node_property_for_field(cls, field, meta_node=False):
        """
        Get the relationship definition for the related node based on field.
        :param field: Field to inspect
        :param meta_node: If True, return the meta node for the related model,
                          else return the model node.
        :returns: A ``RelationshipDefinition`` instance.
        """
        from chemtrails.neoutils import get_node_class_for_model, get_meta_node_class_for_model

        reverse_field = True if isinstance(field, (
            models.ManyToManyRel, models.ManyToOneRel, models.OneToOneRel)) else False

        class DynamicRelation(StructuredRel):
            type = StringProperty(default=field.__class__.__name__)
            is_meta = BooleanProperty(default=meta_node)
            remote_field = StringProperty(default=str('{model}.{field}'.format(
                model=get_model_string(field.model), field=(
                    field.related_name or '%s_set' % field.name
                    if not isinstance(field, models.OneToOneRel) else field.name))
                                                      if reverse_field else field.remote_field.field).lower())
            target_field = StringProperty(default=str(field.target_field).lower())

        prop = cls.get_property_class_for_field(field.__class__)
        relationship_type = cls.get_relationship_type(field)

        if meta_node:
            klass = (__meta_cache__[field.related_model]
                     if field.related_model in __meta_cache__
                     else get_meta_node_class_for_model(field.related_model))
            return prop(cls_name=klass, rel_type=relationship_type, model=DynamicRelation)
        else:
            klass = (__node_cache__[field.related_model]
                     if reverse_field and field.related_model in __node_cache__
                     else get_node_class_for_model(field.related_model))
            return prop(cls_name=klass, rel_type=relationship_type, model=DynamicRelation)


class ModelNodeMixin(ModelNodeMixinBase):

    def __init__(self, instance=None, *args, **kwargs):
        self._instance = instance
        self.__recursion_depth__ = 0

        defaults = {key: getattr(self._instance, key, kwargs.get(key, None))
                    for key, _ in self.__all_properties__}
        kwargs.update(defaults)
        super(ModelNodeMixinBase, self).__init__(self, *args, **kwargs)

        # Query the database for an existing node and set the id if found.
        # This will make this a "bound" node.
        if not hasattr(self, 'id') and getattr(self, 'pk', None) is not None:
            node_id = self._get_id_from_database(self.deflate(self.__properties__))
            if node_id:
                self.id = node_id
            if not self._instance:
                # If instantiated without an instance, try to look it up.
                self._instance = self.get_object(self.pk)

    @property
    def _is_bound(self):
        return getattr(self, 'id', None) is not None

    @property
    def _recursion_depth(self):
        return self.__recursion_depth__

    @_recursion_depth.setter
    def _recursion_depth(self, n):
        self.__recursion_depth__ = n

    def _get_id_from_database(self, params):
        """
        Query for node and return id.
        :param params: Parameters to use in query.
        :returns: Node id if found, else None
        """
        query = ' '.join(('MATCH (n:{label}) WHERE'.format(label=self.__label__),
                          ' AND '.join(['n.{} = {{{}}}'.format(key, key) for key in params.keys()]),
                          'RETURN id(n) LIMIT 1'))
        result, _ = db.cypher_query(query, params)
        return list(flatten(result))[0] if result else None

    def get_object(self, pk=None):
        """
        :returns: Django model instance if found or None
        """
        try:
            return self._instance or ContentType.objects.get(
                app_label=self.app_label, model=self.model_name).get_object_for_this_type(
                pk=pk or getattr(self, 'pk', None))
        except ObjectDoesNotExist:
            return None

    def full_clean(self, exclude=None, validate_unique=True):
        exclude = exclude or []

        props = self.__properties__
        for key in exclude:
            if key in props:
                del props[key]

        try:
            self.deflate(props, self)

            if validate_unique:
                cls = self.__class__
                unique_props = [attr for attr, prop in self.defined_properties(aliases=False, rels=False).items()
                                if prop not in exclude and prop.unique_index]
                for key in unique_props:
                    value = self.deflate({key: props[key]}, self)[key]
                    node = cls.nodes.get_or_none(**{key: value})

                    # If exists and not this node
                    if node and node.id != getattr(self, 'id', None):
                        raise ValidationError({key, 'already exists'})

        except DeflateError as e:
            raise ValidationError({e.property_name: e.msg})
        except RequiredProperty as e:
            raise ValidationError({e.property_name: 'is required'})

    def recursive_connect(self, prop, relation, max_depth, instance=None):
        """
        Recursively connect a related branch.
        :param prop: For example a ``ZeroOrMore`` instance.
        :param relation: ``RelationShipDefinition`` instance
        :param instance: Optional django model instance.
        :param max_depth: Maximum depth of recursive connections to be made.
        :returns: None
        """
        from chemtrails.neoutils import get_node_for_object

        def back_connect(n, depth):
            if n._recursion_depth >= depth:
                return
            n._recursion_depth += 1
            for p, r in n.defined_properties(aliases=False, properties=False).items():
                n.recursive_connect(getattr(n, p), r, max_depth=n._recursion_depth - 1)

        # We require a model instance to look for filter values.
        instance = instance or self.get_object(self.pk)
        if not instance or not hasattr(instance, prop.name):
            return

        klass = relation.definition['node_class']
        source = getattr(instance, prop.name)

        if isinstance(source, models.Model):
            node = klass.nodes.get_or_none(pk=source.pk)
            if not node:
                node = get_node_for_object(source).sync(update_existing=True)
            prop.connect(node)
            back_connect(node, max_depth)

        elif isinstance(source, Manager):
            nodeset = klass.nodes.filter(pk__in=list(source.values_list('pk', flat=True)))
            for node in nodeset:
                prop.connect(node)
                back_connect(node, max_depth)

    def sync(self, max_depth=1, update_existing=True, create_empty=False):
        """
        Synchronizes the current node with data from the database and
        connect all directly related nodes.
        :param max_depth: Maximum depth of recursive connections to be made.
        :param update_existing: If True, save data from the django model to graph node.
        :param create_empty: If the Node has no relational fields, don't create it.
        :returns: The ``ModelNode`` instance or None if not created.
        """
        cls = self.__class__

        if not cls.has_relations and not create_empty:
            return None

        self.full_clean(validate_unique=not update_existing)

        if update_existing:
            if not self._is_bound:
                node = cls.nodes.get_or_none(**{'pk': self.pk})
                if node:
                    self.id = node.id
            self.save()

        # Connect relations
        for prop, relation in self.defined_properties(aliases=False, properties=False).items():
            prop = getattr(self, prop)
            self.recursive_connect(prop, relation, max_depth=max_depth)
        return self


class MetaNodeMeta(NodeBase):
    """
    Meta class for ``ModelRelationNode``.
    """
    def __new__(mcs, name, bases, attrs):
        cls = super(MetaNodeMeta, mcs).__new__(mcs, str(name), bases, attrs)

        # Set label for node
        cls.__label__ = '{object_name}Meta'.format(object_name=cls.Meta.model._meta.object_name)

        # Add some default fields
        cls.type = StringProperty(default='MetaNode')
        cls.app_label = StringProperty(default=cls.Meta.model._meta.app_label)
        cls.model_name = StringProperty(default=cls.Meta.model._meta.model_name)
        cls.default_permissions = ArrayProperty(default=set(itertools.chain(cls.Meta.model._meta.permissions,
                                                                            cls.Meta.model._meta.default_permissions)))

        forward_relations = cls.get_forward_relation_fields()
        reverse_relations = cls.get_reverse_relation_fields()

        # Add to cache before recursively looking up relationships.
        __meta_cache__.update({cls.Meta.model: cls})

        # # Add relations for the model
        for field in itertools.chain(forward_relations, reverse_relations):

            # Add forward relations
            if field in forward_relations:
                relation = cls.get_related_node_property_for_field(field, meta_node=True)
                cls.add_to_class(field.name, relation)

                if settings.CONNECT_META_NODES:
                    node_relation = cls.get_related_node_property_for_field(field, meta_node=False)
                    cls.add_to_class('_%s' % field.name, node_relation)

            # Add reverse relations
            elif field in reverse_relations:
                related_name = field.related_name or '%s_set' % field.name
                relation = cls.get_related_node_property_for_field(field, meta_node=True)
                cls.add_to_class(related_name, relation)

                if settings.CONNECT_META_NODES:
                    node_relation = cls.get_related_node_property_for_field(field, meta_node=False)
                    cls.add_to_class('_%s' % related_name, node_relation)

        # Recalculate definitions
        cls.__all_properties__ = tuple(cls.defined_properties(aliases=False, rels=False).items())
        cls.__all_aliases__ = tuple(cls.defined_properties(properties=False, rels=False).items())
        cls.__all_relationships__ = tuple(cls.defined_properties(aliases=False, properties=False).items())

        install_labels(cls, quiet=True, stdout=None)
        return cls


class MetaNodeMixin(ModelNodeMixin):
    """
    Mixin class for ``StructuredNode`` which adds a number of class methods
    in order to calculate relationship fields from a Django model class.
    """

    def __init__(self, *args, **kwargs):
        self._instance = self.__class__.Meta.model
        self.__recursion_depth__ = 0

        defaults = {key: getattr(self._instance._meta, key, kwargs.get(key, None))
                    for key, _ in self.__all_properties__}
        kwargs.update(defaults)
        StructuredNode.__init__(self, *args, **kwargs)

        if not hasattr(self, 'id'):
            props = self.deflate(self.__properties__)

            # We don't need to match permissions here.
            if 'default_permissions' in props:
                del props['default_permissions']

            node_id = self._get_id_from_database(props)
            if node_id:
                self.id = node_id

    def recursive_connect(self, prop, relation, max_depth):
        """
        Recursively connect a related branch.
        :param prop: For example a ``ZeroOrMore`` instance.
        :param relation: ``RelationShipDefinition`` instance
        :param max_depth: Maximum depth of recursive connections to be made.
        :returns: None
        """
        from chemtrails.neoutils import get_meta_node_for_model

        def back_connect(n, depth):
            if n._recursion_depth >= depth:
                return
            n._recursion_depth += 1
            for p, r in n.defined_properties(aliases=False, properties=False).items():
                n.recursive_connect(getattr(n, p), r, max_depth=n._recursion_depth - 1)

        klass = relation.definition['node_class']
        is_meta = relation.definition['model'].is_meta.default_value()
        if is_meta:
            node = get_meta_node_for_model(klass.Meta.model)
            if not node._is_bound:
                node.save()
            prop.connect(node)
            back_connect(node, max_depth)
        elif not is_meta and settings.CONNECT_META_NODES:
            for node in relation.definition['node_class'].nodes.all():
                prop.connect(node)
                back_connect(node, max_depth)

    def sync(self, max_depth=1, update_existing=True, create_empty=False):
        """
        Synchronizes the current node with data from the database and
        connect all directly related nodes.
        :param max_depth: Maximum depth of recursive connections to be made.
        :param update_existing: If True, save data from the django model to graph node.
        :param create_empty: If the Node has no relational fields, don't create it.
        :returns: The ``MetaNode`` instance or None if not created.
        """
        cls = self.__class__

        if not cls.has_relations and not create_empty:
            return None

        if update_existing:
            if not self._is_bound:
                node = cls.nodes.get_or_none(**{'app_label': self.app_label,
                                                'model_name': self.model_name})
                if node:
                    self.id = node.id
            self.save()

        # Connect relations
        for prop, relation in self.defined_properties(aliases=False, properties=False).items():
            prop = getattr(self, prop)
            self.recursive_connect(prop, relation, max_depth=max_depth)
        return self

