from __future__ import absolute_import, print_function

from django.db import models

from sentry.db.models import FlexibleForeignKey, Model, sane_repr


class Commit(Model):
    __core__ = False

    project = FlexibleForeignKey('sentry.Project')
    key = models.CharField(max_length=64)
    author = FlexibleForeignKey('sentry.CommitAuthor')
    message = models.TextField()

    class Meta:
        app_label = 'sentry'
        db_table = 'sentry_commit'
        unique_together = (('project', 'key'),)

    __repr__ = sane_repr('project_id', 'key')
