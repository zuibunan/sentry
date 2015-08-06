from __future__ import absolute_import, print_function

from django.db import models

from sentry.db.models import FlexibleForeignKey, Model, sane_repr


class CommitAuthor(Model):
    __core__ = False

    project = FlexibleForeignKey('sentry.Project')
    name = models.CharField(max_length=128, null=True)
    email = models.EmailField()

    class Meta:
        app_label = 'sentry'
        db_table = 'sentry_commitauthor'
        unique_together = (('project', 'email'),)

    __repr__ = sane_repr('project_id', 'email', 'name')
