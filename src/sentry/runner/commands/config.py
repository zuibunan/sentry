"""
sentry.runner.commands.config
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

:copyright: (c) 2015 by the Sentry Team, see AUTHORS for more details.
:license: BSD, see LICENSE for more details.
"""
from __future__ import absolute_import, print_function

import itertools

import click
from sentry.runner.decorators import configuration


@click.group()
def config():
    "Manage runtime config options."


@config.command()
@click.argument('pattern', default='*', required=False)
@configuration
def list(pattern):
    "List configuration options."
    from fnmatch import fnmatch
    from sentry.options import default_manager as manager
    for key in manager.all():
        if fnmatch(key.name, pattern):
            click.echo('%s %s' % (key.name, key.type.name.upper()))


@config.command()
@click.option('--silent', '-q', default=False, is_flag=True, help='Suppress extraneous output.')
@click.argument('option')
@configuration
def get(option, silent):
    "Get a configuration option."
    from django.conf import settings
    from sentry.options import default_manager as manager
    from sentry.options.manager import UnknownOption
    try:
        key = manager.lookup_key(option)
    except UnknownOption:
        raise click.ClickException('unknown option: %s' % option)
    value = manager.get(key.name)
    if silent:
        click.echo(value)
        return
    # TODO(mattrobenolt): Add help to option keys
    # if key.help:
    #     click.echo(key.help + '\n')
    click.echo('        type: %s' % key.type.name.upper())
    click.echo(' from config: %s' % settings.SENTRY_OPTIONS.get(key.name, '<not set>'))
    click.echo('     current: %s' % value)


@config.command()
@click.argument('option')
@click.argument('value')
@configuration
def set(option, value):
    "Set a configuration option to a new value."
    from sentry import options
    from sentry.options.manager import UnknownOption
    try:
        options.set(option, value)
    except UnknownOption:
        raise click.ClickException('unknown option: %s' % option)
    except TypeError as e:
        raise click.ClickException(unicode(e))


@config.command()
@click.option('--no-input', default=False, is_flag=True, help='Do not show confirmation.')
@click.argument('option')
@configuration
def delete(option, no_input):
    "Delete/unset a configuration option."
    from sentry import options
    from sentry.options.manager import UnknownOption
    if not no_input:
        click.confirm('Are you sure you want to delete "%s"?' % option, default=False, abort=True)
    try:
        options.delete(option)
    except UnknownOption:
        raise click.ClickException('unknown option: %s' % option)


@config.command()
def migrate():
    # XXX: Note that this does **not** have the `configuration` decorator,
    # since it requires the settings to not already be patched.
    from sentry.runner.settings import discover_configs, load_django_settings

    _, py, yaml = discover_configs()

    settings = load_django_settings(py)

    from sentry.conf.server import DEAD
    from sentry.options import load_defaults
    from sentry.runner.initializer import (
        load_options_from_file,
        forward_options_mapper,
        writeback_options_mapper,
    )

    load_defaults()

    options = load_options_from_file(yaml)

    options_mapper = itertools.chain(
        forward_options_mapper.iteritems(),
        writeback_options_mapper.iteritems(),
    )

    migrated = {}
    for configuration_key, setting_name in options_mapper:
        value = getattr(settings, setting_name, DEAD)
        if value is not DEAD and configuration_key not in options:
            migrated[configuration_key] = (setting_name, value)

    import yaml

    # TODO: Actually append these to the source files.

    for key, (setting_name, value) in sorted(migrated.items()):
        print('# This setting was automatically migrated from {}.'.format(setting_name))
        print(yaml.safe_dump({key: value}, default_flow_style=False))

    # TODO: Handle Redis.


@config.command(name='generate-secret-key')
def generate_secret_key():
    "Generate a new cryptographically secure secret key value."
    from sentry.runner.settings import generate_secret_key
    click.echo(generate_secret_key())
