"""
sentry.rules.helpers
~~~~~~~~~~~~~~~~~~~~~

:copyright: (c) 2010-2014 by the Sentry Team, see AUTHORS for more details.
:license: BSD, see LICENSE for more details.
"""

from __future__ import absolute_import

__all__ = ('get_rules', 'apply_rule')

import logging

from sentry.models import Rule, GroupRuleStatus
from sentry.rules import rules
from sentry.utils.cache import cache
from sentry.utils.safe import safe_execute


rules_logger = logging.getLogger('sentry.errors.rules')


def get_rules(project):
    cache_key = 'project:%d:rules' % (project.id,)
    rules_list = cache.get(cache_key)
    if rules_list is None:
        rules_list = list(Rule.objects.filter(project=project))
        cache.set(cache_key, rules_list, 60)
    return rules_list


def condition_matches(project, condition, event, state, rule_is_active):
    condition_cls = rules.get(condition['id'])
    if condition_cls is None:
        rules_logger.error('Unregistered condition %r', condition['id'])
        return

    condition_inst = condition_cls(project, data=condition)
    return safe_execute(condition_inst.passes, event, state, rule_is_active)


def get_matching_rules(event, state):
    project = event.project
    group = event.group

    matches = []
    for rule in get_rules(project):
        match = rule.data.get('action_match', 'all')
        condition_list = rule.data.get('conditions', ())

        if not condition_list:
            continue

        # TODO(dcramer): this might not make sense for other rule actions
        # so we should find a way to abstract this into actions
        # TODO(dcramer): this isnt the most efficient query pattern for this
        if group:
            rule_status, _ = GroupRuleStatus.objects.get_or_create(
                rule=rule,
                group=group,
                defaults={
                    'project': project,
                    'status': GroupRuleStatus.INACTIVE,
                },
            )
            rule_is_active = rule_status.status == GroupRuleStatus.ACTIVE
        else:
            rule_is_active = False

        condition_iter = (
            condition_matches(project, c, event, state, rule_is_active)
            for c in condition_list
        )

        if match == 'all':
            passed = all(condition_iter)
        elif match == 'any':
            passed = any(condition_iter)
        elif match == 'none':
            passed = not any(condition_iter)
        else:
            rules_logger.error('Unsupported action_match %r for rule %d',
                               match, rule.id)
            continue

        if group:
            # HACK(dcramer): this is fairly dirty and we need to find a better way
            # to work around this behavior
            if passed and rule_status.status == GroupRuleStatus.INACTIVE:
                # we only fire if we're able to say that the state has changed
                GroupRuleStatus.objects.filter(
                    id=rule.id,
                    group=group.id,
                    status=GroupRuleStatus.INACTIVE,
                ).update(status=GroupRuleStatus.ACTIVE)

            elif not passed and rule_status.status == GroupRuleStatus.ACTIVE:
                # update the state to suggest this rule can fire again
                GroupRuleStatus.objects.filter(
                    id=rule.id,
                    group=group.id,
                    status=GroupRuleStatus.ACTIVE,
                ).update(status=GroupRuleStatus.INACTIVE)

        if passed:
            matches.append(rule)
    return matches


def apply_rule(rule, event, state, clause):
    assert clause in ('before', 'after')

    project = event.project

    for action in rule.data.get('actions', ()):
        action_cls = rules.get(action['id'])
        if action_cls is None:
            rules_logger.error('Unregistered action %r', action['id'])
            continue

        action_inst = action_cls(project, data=action)
        safe_execute(getattr(action_inst, clause), event=event, state=state)
