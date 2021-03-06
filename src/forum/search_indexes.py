# encoding: utf-8

from haystack.indexes import *
from haystack import site

from . import models


class PostIndex(SearchIndex):
    text = CharField(document=True, use_template=True)
    author = CharField(model_attr='user')
    created = DateTimeField(model_attr='created')
    topic = CharField(model_attr='topic')
    category = CharField(model_attr='topic__forum__category__name')
    forum = IntegerField(model_attr='topic__forum__pk')

site.register(models.Post, PostIndex)
