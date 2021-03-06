# -*- coding: utf-8 -*-

from django.utils import six

from neomodel import *
from chemtrails.neoutils.core import (
    ModelNodeMeta, ModelNodeMixin,
    MetaNodeMeta, MetaNodeMixin
)

__all__ = [
    'get_meta_node_class_for_model',
    'get_node_class_for_model',
    'get_node_for_object',
    'model_cache'
]
model_cache = {}


def get_meta_node_class_for_model(model):
    """
    Meta nodes are used to generate a map of the relationships
    in the database. There's only a single MetaNode per model.
    :param model: Django model class.
    :returns: A ``StructuredNode`` class.
    """
    cache_key = '{object_name}RelationMeta'.format(object_name=model._meta.object_name)
    if cache_key in model_cache:
        return model_cache[cache_key]
    else:
        @six.add_metaclass(MetaNodeMeta)
        class MetaNode(MetaNodeMixin, StructuredNode):
            __metaclass_model__ = model

            class Meta:
                model = None  # Will pick model from parent class __metaclass_model__ attribute

        model_cache[cache_key] = MetaNode
        return MetaNode


def get_meta_node_for_model(model):
    """
    Get a ``MetaNode`` instance for the current model class.
    :param model: Django model class.
    :returns: A ``MetaNode`` instance.
    """
    klass = get_meta_node_class_for_model(model)
    return klass()


def get_node_class_for_model(model):
    """
    Model nodes represent a model instance in the database.
    :param model: Django model class.
    :returns: A ``ModelNode`` class.
    """
    cache_key = '{object_name}Node'.format(object_name=model._meta.object_name)
    if cache_key in model_cache:
        return model_cache[cache_key]
    else:
        @six.add_metaclass(ModelNodeMeta)
        class ModelNode(ModelNodeMixin, StructuredNode):
            __metaclass_model__ = model

            class Meta:
                model = None  # Will pick model from parent class __metaclass_model__ attribute

        model_cache[cache_key] = ModelNode
        return ModelNode


def get_node_for_object(instance):
    """
    Get a ``ModelNode`` instance for the current object instance.
    :param instance: Django model instance.
    :returns: A ``ModelNode`` instance.
    """
    klass = get_node_class_for_model(instance._meta.model)
    return klass(instance=instance)


def get_nodeset_for_queryset(queryset, sync=False, max_depth=1):
    """
    Get a ``NodeSet`` instance for the current queryset instance.
    :param queryset: Django ``QuerySet`` instance.
    :param sync: Sync all items in the queryset before returning.
    :param max_depth: Maximum depth of recursive connections to be made
                      while syncing each node in the nodeset.
    :returns: A ``neomodel.match.NodeSet`` instance.
    """
    klass = get_node_class_for_model(queryset.model)
    nodeset = klass.nodes.filter(pk__in=list(queryset.values_list('pk', flat=True)))
    if sync:
        for instance in queryset:
            get_node_for_object(instance).sync(max_depth=max_depth, update_existing=True)
        nodeset = get_nodeset_for_queryset(queryset, sync=False)
    return nodeset


