# -*- coding: utf-8 -*-

import itertools
import operator
from functools import reduce

from django.apps import apps
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import models
from django.db.models import Manager

from neomodel import *


field_property_map = {
    models.ForeignKey: RelationshipTo,
    models.OneToOneField: Relationship,
    models.ManyToManyField: RelationshipTo,
    models.ManyToOneRel: RelationshipFrom,
    models.OneToOneRel: RelationshipFrom,
    models.ManyToManyRel: RelationshipFrom,

    models.AutoField: IntegerProperty,
    models.BigAutoField: IntegerProperty,
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


def get_model_string(model):
    """
    :param model: model
    :returns: <app_label>.<model_name> string representation for the model
    """
    return "{app_label}.{model_name}".format(app_label=model._meta.app_label, model_name=model._meta.model_name)


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
            module = attrs.get('__module__')
            meta = Meta('Meta', (Meta,), dict(cls.Meta.__dict__))

            # A little hack which helps us dynamically create ModelNode classes
            # where variables holding the model class is out of scope.
            if hasattr(cls, '__metaclass_model__') and not meta.model:
                meta.model = getattr(cls, '__metaclass_model__', None)
                delattr(cls, '__metaclass_model__')

            if not getattr(meta, 'model', None):
                raise ValueError('%s.Meta.model attribute cannot be None.' % name)

            if getattr(meta, 'app_label', None) is None:
                app_config = apps.get_containing_app_config(module)
                if app_config is None:
                    raise RuntimeError(
                        "ModelNode class %s.%s doesn't declare an explicit "
                        "app_label and isn't in an application in "
                        "INSTALLED_APPS." % (module, name)
                    )
                else:
                    meta.app_label = app_config.label

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
        cls.pk = cls.get_property_class_for_field(cls._pk_field.__class__)(unique_index=True)
        cls.model = StringProperty(default=get_model_string(cls.Meta.model))
        cls.app_label = StringProperty(default=cls.Meta.app_label)

        forward_relations = cls.get_forward_relation_fields()
        reverse_relations = cls.get_reverse_relation_fields()

        for field in cls.Meta.model._meta.get_fields():

            # Add forward relations
            if field in forward_relations:
                # TODO: Figure out how to avoid infinity loops on self referencing fields.
                if hasattr(field, 'to') and field.to == cls.Meta.model:
                    continue
                relationship = cls.get_related_node_property_for_field(field)
                cls.add_to_class(field.name, relationship)

            # Add reverse relations
            elif field in reverse_relations:
                # TODO: Figure out how to avoid infinity loops on reverse relations.
                # NOTE: Seems hard to avoid... =(
                if hasattr(field, 'to') and field.to == cls.Meta.model:
                    continue
                # The following block never triggers, but are left here to demonstrate how
                # I'd like to do it...
                related_name = field.related_name or '%s_set' % field.name
                relationship = cls.get_related_node_property_for_field(field)
                cls.add_to_class(related_name, relationship)

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


class ModelNodeMixinBase(object):
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
    def get_relation_fields(model):
        """
        Get a list of fields on the model which represents relations.
        """
        return [
            field for field in model._meta.get_fields()
            if field.is_relation or field.one_to_one or (field.many_to_one and field.related_model)
        ]

    @staticmethod
    def get_property_class_for_field(klass):
        """
        Returns the appropriate property class for field class.
        """
        if klass in field_property_map:
            return field_property_map[klass]
        return None

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
            remote_field = StringProperty(default=str(field.remote_field if reverse_field
                                                      else field.remote_field.field).lower())
            target_field = StringProperty(default=str(field.target_field).lower())

        relationship_type = {
            Relationship: 'MUTUAL',
            RelationshipTo: 'FORWARD',
            RelationshipFrom: 'REVERSE'
        }
        prop = cls.get_property_class_for_field(field.__class__)

        if meta_node:
            klass = get_meta_node_class_for_model(field.remote_field.related_model)
            return prop(cls_name=klass, rel_type=relationship_type[prop], model=DynamicRelation)

        klass = get_node_class_for_model(field.related_model)
        return prop(cls_name=klass, rel_type=relationship_type[prop], model=DynamicRelation)

    @classmethod
    def get_meta_node_property_for_field(cls, field):
        pass

    @classmethod
    def create_or_update_one(cls, *props, **kwargs):
        """
        Call to MERGE with parameters map to create or update a single _instance. A new _instance
        will be created and saved if it does not already exists. If an _instance already exists,
        all optional properties specified will be updated.
        :param props: List of dict arguments to get or create the entity with.
        :keyword relationship: Optional, relationship to get/create on when new entity is created.
        :keyword lazy: False by default, specify True to get node with id only without the parameters.
        :returns: A single ``StructuredNode` _instance.
        """
        with db.transaction:
            result = cls.create_or_update(*props, **kwargs)
            if len(result) > 1:
                raise MultipleNodesReturned(
                    'sync() returned more than one {klass} - it returned {num}.'.format(
                        klass=cls.__class__.__name__, num=len(result)))
            elif not result:
                raise cls.DoesNotExist(
                    '{klass} was unable to sync - Did not receive any results.'.format(
                        klass=cls.__class__.__name__))

            # There should be exactly one node.
            result = result[0]
        return result


class ModelNodeMixin(ModelNodeMixinBase):

    def __init__(self, instance=None, *args, **kwargs):
        self._instance = instance
        for key, _ in self.__all_properties__:
            kwargs[key] = getattr(self._instance, key, kwargs.get(key, None))
        super(ModelNodeMixinBase, self).__init__(self, *args, **kwargs)

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
                unique_props = [attr for attr, prop in cls.defined_properties(aliases=False, rels=False).items()
                                if prop not in exclude and prop.unique_index]
                for key in unique_props:
                    value = self.deflate({key: props[key]}, self)[key]
                    node = cls.nodes.get_or_none(**{key: value})

                    # if exists and not this node
                    if node and node.id != getattr(self, 'id', None):
                        raise ValidationError({key, 'already exists'})

        except DeflateError as e:
            raise ValidationError({e.property_name: e.msg})
        except RequiredProperty as e:
            raise ValidationError({e.property_name: 'is required'})

    def sync(self, update_existing=True):
        from chemtrails.neoutils import get_node_for_object, get_node_class_for_model
        self.full_clean(validate_unique=not update_existing)

        cls = self.__class__
        node = cls.nodes.get_or_none(**{'pk': self.pk})

        # If found, steal the id. This will cause the existing node to
        # be saved with data from this _instance.
        if node and update_existing:
            self.id = node.id

        self.save()

        # Connect relations
        for field_name, _ in cls.defined_properties(aliases=False, properties=False).items():
            field = getattr(self, field_name)

            # TODO: Connect meta
            # field.connect(cls._cache[field.name])

            # Connect related nodes
            if self._instance and hasattr(self._instance, field.name):
                attr = getattr(self._instance, field.name)

                if isinstance(attr, models.Model):
                    node = get_node_for_object(attr).sync(update_existing=True)
                    field.connect(node)
                elif isinstance(attr, Manager):
                    klass = get_node_class_for_model(attr.model)
                    related_nodes = klass.nodes.filter(pk__in=list(attr.values_list('pk', flat=True)))
                    for n in related_nodes:
                        field.connect(n)
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
        cls.model = StringProperty(unique_index=True, default=get_model_string(cls.Meta.model))

        forward_relations = cls.get_forward_relation_fields()
        reverse_relations = cls.get_reverse_relation_fields()

        # Add relations for the model
        for field in itertools.chain(forward_relations, reverse_relations):
            if hasattr(field, 'field') and field.field.__class__ in field_property_map:
                relationship = cls.get_related_node_property_for_field(field.field, meta_node=True)
                cls.add_to_class(field.name, relationship)

        # Recalculate definitions
        cls.__all_properties__ = tuple(cls.defined_properties(aliases=False, rels=False).items())
        cls.__all_aliases__ = tuple(cls.defined_properties(properties=False, rels=False).items())
        cls.__all_relationships__ = tuple(cls.defined_properties(aliases=False, properties=False).items())

        install_labels(cls, quiet=True, stdout=None)
        return cls


class MetaNodeMixin(ModelNodeMixinBase):
    """
    Mixin class for ``StructuredNode`` which adds a number of class methods
    in order to calculate relationship fields from a Django model class.
    """

    @classmethod
    def sync(cls, **kwargs):
        """
        Write meta node to the graph and create all relationships.
        :param kwargs: Mapping of keyword arguments which will be passed to ``create_or_update_one()``
        :returns: ``MetaNode`` instance.
        """
        node = cls.create_or_update_one([{'model': get_model_string(cls.Meta.model)}], **kwargs)
        if node.has_relations:
            for field_name, relationship in cls.defined_properties(aliases=False, properties=False).items():
                field = getattr(node, field_name)
                related_node = relationship.definition['node_class'].sync()
                field.connect(related_node)
        return node
