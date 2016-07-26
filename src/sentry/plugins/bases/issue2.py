from rest_framework.response import Response
from social_auth.models import UserSocialAuth

from django.conf import settings
from django.conf.urls import patterns, url
from django.core.urlresolvers import reverse
from django.utils.html import format_html

from sentry.api.bases.group import GroupEndpoint
from sentry.api.bases.project import ProjectEndpoint
from sentry.models import Activity, Event, GroupMeta
from sentry.plugins import Plugin
from sentry.plugins.base.configuration import default_issue_plugin_config
from sentry.signals import issue_tracker_used
from sentry.utils.auth import get_auth_providers
from sentry.utils.http import absolute_uri
from sentry.utils.safe import safe_execute


class PluginError(Exception):
    pass


class IssueGroupActionEndpoint(GroupEndpoint):
    view_method_name = None
    plugin = None

    def _handle(self, request, group, *args, **kwargs):
        GroupMeta.objects.populate_cache([group])

        return getattr(self.plugin, self.view_method_name)(request, group, *args, **kwargs)

    def get(self, request, group, *args, **kwargs):
        return self._handle(request, group, *args, **kwargs)

    def post(self, request, group, *args, **kwargs):
        return self._handle(request, group, *args, **kwargs)


class IssuePluginProjectEndpoint(ProjectEndpoint):
    view_method_name = None
    plugin = None

    def _handle(self, request, project, *args, **kwargs):
        return getattr(self.plugin, self.view_method_name)(request, project, *args, **kwargs)

    def get(self, request, project, *args, **kwargs):
        return self._handle(request, project, *args, **kwargs)

    def post(self, request, project, *args, **kwargs):
        return self._handle(request, project, *args, **kwargs)


class IssueTrackingPlugin2(Plugin):
    auth_provider = None
    allowed_actions = ('create', 'link', 'unlink')

    def has_project_conf(self):
        return True

    def get_group_urls(self):
        _urls = []
        for action in self.allowed_actions:
            view_method_name = 'view_%s' % action
            _urls.append(url(r'^(?:issues|groups)/(?P<issue_id>\d+)/plugin/{action}/{slug}/'.format(action=action, slug=self.slug),
                             IssueGroupActionEndpoint.as_view(view_method_name=view_method_name, plugin=self)))

        return patterns('', *_urls)

    def get_project_urls(self):
        _urls = []
        # TODO: add enable here when moved to api
        for action in ('configure', 'disable'):
            view_method_name = 'view_%s' % action
            _urls.append(url(r'^projects/(?P<organization_slug>[^\/]+)/(?P<project_slug>[^\/]+)/plugin/{action}/{slug}'.format(action=action, slug=self.slug),
                             IssuePluginProjectEndpoint.as_view(view_method_name=view_method_name, plugin=self)))

        return patterns('', *_urls)

    def _get_group_body(self, request, group, event, **kwargs):
        result = []
        for interface in event.interfaces.itervalues():
            output = safe_execute(interface.to_string, event, _with_transaction=False)
            if output:
                result.append(output)
        return '\n\n'.join(result)

    def _get_group_description(self, request, group, event):
        output = [
            absolute_uri(group.get_absolute_url()),
        ]
        body = self._get_group_body(request, group, event)
        if body:
            output.extend([
                '',
                '```',
                body,
                '```',
            ])
        return '\n'.join(output)

    def _get_group_title(self, request, group, event):
        return event.error()

    def is_configured(self, request, project, **kwargs):
        raise NotImplementedError

    def get_auth_for_user(self, user, **kwargs):
        """
        Return a ``UserSocialAuth`` object for the given user based on this plugins ``auth_provider``.
        """
        assert self.auth_provider, 'There is no auth provider configured for this plugin.'

        if not user.is_authenticated():
            return None

        try:
            return UserSocialAuth.objects.filter(user=user, provider=self.auth_provider)[0]
        except IndexError:
            return None

    def needs_auth(self, request, project, **kwargs):
        """
        Return ``True`` if the authenticated user needs to associate an auth service before
        performing actions with this plugin.
        """
        if self.auth_provider is None:
            return False

        if not request.user.is_authenticated():
            return True

        return bool(not UserSocialAuth.objects.filter(user=request.user, provider=self.auth_provider).exists())

    def get_new_issue_fields(self, request, group, event, **kwargs):
        """
        If overriding, supported properties include 'readonly': true
        """
        return [{
            'name': 'title',
            'label': 'Title',
            'default': self._get_group_title(request, group, event),
            'type': 'text'
        }, {
            'name': 'description',
            'label': 'Description',
            'default': self._get_group_description(request, group, event),
            'type': 'textarea'
        }]

    def get_link_existing_issue_fields(self, request, group, event, **kwargs):
        return []

    def get_configure_plugin_fields(self, request, project, **kwargs):
        """
        Must be overridden by plugins that require configuration.
        """
        raise NotImplementedError

    def get_issue_url(self, group, issue_id, **kwargs):
        """
        Given an issue_id (string) return an absolute URL to the issue's details
        page.
        """
        raise NotImplementedError

    # TODO: should this return more than just title?
    def get_issue_title_by_id(self, request, group, issue_id):
        """
        Given an issue_id return the issue's title.
        """
        raise NotImplementedError

    def get_issue_label(self, group, issue_id, **kwargs):
        """
        Given an issue_id (string) return a string representing the issue.

        e.g. GitHub represents issues as GH-XXX
        """
        return '#%s' % issue_id

    def create_issue(self, request, group, form_data, **kwargs):
        """
        Creates the issue on the remote service and returns an issue ID.
        """
        raise NotImplementedError

    def link_issue(self, request, group, form_data, **kwargs):
        """
        Can be overridden for any actions needed when linking issues
        (like adding a comment to an existing issue).
        """
        pass

    def has_auth_configured(self, **kwargs):
        if not self.auth_provider:
            return True

        return self.auth_provider in get_auth_providers()

    def validate_form(self, fields, form_data):
        errors = {}
        for field in fields:
            if field.get('required', True) and not field.get('readonly'):
                value = form_data.get(field['name'])
                if value is None or value == '':
                    errors[field['name']] = u'%s is a required field.' % field['label']
        return errors

    def view_create(self, request, group, **kwargs):
        auth_errors = self.check_config_and_auth(request, group)
        if auth_errors:
            return Response(auth_errors, status=400)

        event = group.get_latest_event()
        Event.objects.bind_nodes([event], 'data')
        fields = self.get_new_issue_fields(request, group, event, **kwargs)
        if request.method == 'GET':
            return Response(fields)

        errors = self.validate_form(fields, request.DATA)
        if errors:
            return Response({
                'error_type': 'validation',
                'errors': errors
            }, status=400)

        try:
            issue_id = self.create_issue(
                group=group,
                form_data=request.DATA,
                request=request,
            )
        except PluginError as e:
            return Response({
                'error_type': 'validation',
                'errors': [{'__all__': e.message}]
            })
        GroupMeta.objects.set_value(group, '%s:tid' % self.get_conf_key(), issue_id)

        issue_information = {
            'title': request.DATA['title'],
            'provider': self.get_title(),
            'location': self.get_issue_url(group, issue_id),
            'label': self.get_issue_label(group=group, issue_id=issue_id),
        }
        Activity.objects.create(
            project=group.project,
            group=group,
            type=Activity.CREATE_ISSUE,
            user=request.user,
            data=issue_information,
        )

        issue_tracker_used.send(plugin=self, project=group.project, user=request.user, sender=IssueTrackingPlugin2)
        return Response({'issue_url': self.get_issue_url(group=group, issue_id=issue_id)})

    def view_unlink(self, request, group, **kwargs):
        auth_errors = self.check_config_and_auth(request, group)
        if auth_errors:
            return Response(auth_errors, status=400)
        if GroupMeta.objects.get_value(group, '%s:tid' % self.get_conf_key(), None):
            if 'unlink' in self.allowed_actions:
                GroupMeta.objects.unset_value(group, '%s:tid' % self.get_conf_key())
                return Response({'message': 'Successfully unlinked issue.'})
        return Response({'message': 'No issues to unlink.'}, status=400)

    def view_link(self, request, group, **kwargs):
        auth_errors = self.check_config_and_auth(request, group)
        if auth_errors:
            return Response(auth_errors, status=400)
        event = group.get_latest_event()
        Event.objects.bind_nodes([event], 'data')
        fields = self.get_link_existing_issue_fields(request, group, event, **kwargs)
        if request.method == 'GET':
            return Response(fields)
        errors = self.validate_form(fields, request.DATA)
        if errors:
            return Response({
                'error_type': 'validation',
                'errors': errors
            }, status=400)
        try:
            self.link_issue(
                group=group,
                form_data=request.DATA,
                request=request,
            )
        except PluginError as e:
            return Response({
                'error_type': 'validation',
                'errors': [{'__all__': e.message}]
            })

        issue_id = int(request.DATA['issue_id'])
        GroupMeta.objects.set_value(group, '%s:tid' % self.get_conf_key(), issue_id)
        issue_information = {
            'title': self.get_issue_title_by_id(request, group, issue_id),
            'provider': self.get_title(),
            'location': self.get_issue_url(group, issue_id),
            'label': self.get_issue_label(group=group, issue_id=issue_id),
        }
        Activity.objects.create(
            project=group.project,
            group=group,
            type=Activity.CREATE_ISSUE,
            user=request.user,
            data=issue_information,
        )
        return Response({'message': 'Successfully linked issue.'})

    def view_configure(self, request, project, **kwargs):
        if request.method == 'GET':
            return Response(self.get_configure_plugin_fields(request, project, **kwargs))
        self.configure(project, request.DATA)
        return Response({'message': 'Successfully updated configuration.'})

    def configure(self, project, form_data):
        """Configures the plugin"""
        default_issue_plugin_config(self, project, form_data)

    def view_disable(self, request, project, **kwargs):
        if self.can_disable:
            self.disable(project)
            return Response({'message': 'Successfully disabled plugin'})
        return Response({'message': 'Plugin cannot be disabled'}, status=400)

    def check_config_and_auth(self, request, group):
        has_auth_configured = self.has_auth_configured()
        if not (has_auth_configured and self.is_configured(project=group.project, request=request)):
            if self.auth_provider:
                required_auth_settings = settings.AUTH_PROVIDERS[self.auth_provider]
            else:
                required_auth_settings = None

            return {
                'error_type': 'config',
                'title': self.get_title(),
                'slug': self.slug,
                'has_auth_configured': has_auth_configured,
                'auth_provider': self.auth_provider,
                'required_auth_settings': required_auth_settings,
            }

        if self.needs_auth(project=group.project, request=request):
            return {
                'error_type': 'auth',
                'title': self.get_title(),
                'auth_url': reverse('socialauth_associate_begin', args=[self.auth_provider])
            }

    def plugin_issues(self, request, group, plugin_issues, **kwargs):
        if not self.is_configured(request=request, project=group.project):
            return plugin_issues
        prefix = self.get_conf_key()
        issue_id = GroupMeta.objects.get_value(group, '%s:tid' % prefix, None)
        item = {
            'slug': self.slug,
            'allowed_actions': self.allowed_actions,
            'title': self.get_title()
        }
        if issue_id:
            item['issue'] = {
                'issue_id': issue_id,
                'url': self.get_issue_url(group=group, issue_id=issue_id),
                'label': self.get_issue_label(group=group, issue_id=issue_id),
            }
        plugin_issues.append(item)
        return plugin_issues

    # TODO: should we get rid of this (move it to react?)
    def tags(self, request, group, tag_list, **kwargs):
        if not self.is_configured(request=request, project=group.project):
            return tag_list

        prefix = self.get_conf_key()
        issue_id = GroupMeta.objects.get_value(group, '%s:tid' % prefix)
        if not issue_id:
            return tag_list

        tag_list.append(format_html('<a href="{}">{}</a>',
            self.get_issue_url(group=group, issue_id=issue_id),
            self.get_issue_label(group=group, issue_id=issue_id),
        ))

        return tag_list

IssuePlugin2 = IssueTrackingPlugin2
