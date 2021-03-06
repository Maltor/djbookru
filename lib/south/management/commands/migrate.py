"""
Migrate management command.
"""

from __future__ import print_function

import os.path, re, sys
from functools import reduce
from optparse import make_option

from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils.importlib import import_module

from south import migration
from south.migration import Migrations
from south.exceptions import NoMigrations
from south.db import DEFAULT_DB_ALIAS

class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option('--all', action='store_true', dest='all_apps', default=False,
            help='Run the specified migration for all apps.'),
        make_option('--list', action='store_true', dest='show_list', default=False,
            help='List migrations noting those that have been applied'),
        make_option('--changes', action='store_true', dest='show_changes', default=False,
            help='List changes for migrations'),
        make_option('--skip', action='store_true', dest='skip', default=False,
            help='Will skip over out-of-order missing migrations'),
        make_option('--merge', action='store_true', dest='merge', default=False,
            help='Will run out-of-order missing migrations as they are - no rollbacks.'),
        make_option('--no-initial-data', action='store_true', dest='no_initial_data', default=False,
            help='Skips loading initial data if specified.'),
        make_option('--fake', action='store_true', dest='fake', default=False,
            help="Pretends to do the migrations, but doesn't actually execute them."),
        make_option('--db-dry-run', action='store_true', dest='db_dry_run', default=False,
            help="Doesn't execute the SQL generated by the db methods, and doesn't store a record that the migration(s) occurred. Useful to test migrations before applying them."),
        make_option('--delete-ghost-migrations', action='store_true', dest='delete_ghosts', default=False,
            help="Tells South to delete any 'ghost' migrations (ones in the database but not on disk)."),
        make_option('--ignore-ghost-migrations', action='store_true', dest='ignore_ghosts', default=False,
            help="Tells South to ignore any 'ghost' migrations (ones in the database but not on disk) and continue to apply new migrations."),
        make_option('--noinput', action='store_false', dest='interactive', default=True,
            help='Tells Django to NOT prompt the user for input of any kind.'),
        make_option('--database', action='store', dest='database',
            default=DEFAULT_DB_ALIAS, help='Nominates a database to synchronize. '
                'Defaults to the "default" database.'),
    )
    if '--verbosity' not in [opt.get_opt_string() for opt in BaseCommand.option_list]:
        option_list += (
            make_option('--verbosity', action='store', dest='verbosity', default='1',
            type='choice', choices=['0', '1', '2'],
            help='Verbosity level; 0=minimal output, 1=normal output, 2=all output'),
        )
    help = "Runs migrations for all apps."
    args = "[appname] [migrationname|zero] [--all] [--list] [--skip] [--merge] [--no-initial-data] [--fake] [--db-dry-run] [--database=dbalias]"

    def handle(self, app=None, target=None, skip=False, merge=False, backwards=False, fake=False, db_dry_run=False, show_list=False, show_changes=False, database=DEFAULT_DB_ALIAS, delete_ghosts=False, ignore_ghosts=False, **options):

        # NOTE: THIS IS DUPLICATED FROM django.core.management.commands.syncdb
        # This code imports any module named 'management' in INSTALLED_APPS.
        # The 'management' module is the preferred way of listening to post_syncdb
        # signals, and since we're sending those out with create_table migrations,
        # we need apps to behave correctly.
        for app_name in settings.INSTALLED_APPS:
            try:
                import_module('.management', app_name)
            except ImportError as exc:
                msg = exc.args[0]
                if not msg.startswith('No module named') or 'management' not in msg:
                    raise
        # END DJANGO DUPE CODE

        # if all_apps flag is set, shift app over to target
        if options.get('all_apps', False):
            target = app
            app = None

        # Migrate each app
        if app:
            try:
                apps = [Migrations(app)]
            except NoMigrations:
                print("The app '%s' does not appear to use migrations." % app)
                print("./manage.py migrate " + self.args)
                return
        else:
            apps = list(migration.all_migrations())

        # Do we need to show the list of migrations?
        if show_list and apps:
            list_migrations(apps, database, **options)

        if show_changes and apps:
            show_migration_changes(apps)

        if not (show_list or show_changes):

            for app in apps:
                result = migration.migrate_app(
                    app,
                    target_name = target,
                    fake = fake,
                    db_dry_run = db_dry_run,
                    verbosity = int(options.get('verbosity', 0)),
                    interactive = options.get('interactive', True),
                    load_initial_data = not options.get('no_initial_data', False),
                    merge = merge,
                    skip = skip,
                    database = database,
                    delete_ghosts = delete_ghosts,
                    ignore_ghosts = ignore_ghosts,
                )
                if result is False:
                    sys.exit(1) # Migration failed, so the command fails.


def list_migrations(apps, database = DEFAULT_DB_ALIAS, **options):
    """
    Prints a list of all available migrations, and which ones are currently applied.
    Accepts a list of Migrations instances.
    """
    from south.models import MigrationHistory
    applied_migrations = MigrationHistory.objects.filter(app_name__in=[app.app_label() for app in apps])
    if database != DEFAULT_DB_ALIAS:
        applied_migrations = applied_migrations.using(database)
    applied_migration_names = ['%s.%s' % (mi.app_name,mi.migration) for mi in applied_migrations]

    print()
    for app in apps:
        print(" " + app.app_label())
        # Get the migrations object
        for migration in app:
            if migration.app_label() + "." + migration.name() in applied_migration_names:
                applied_migration = applied_migrations.get(app_name=migration.app_label(), migration=migration.name())
                print(format_migration_list_item(migration.name(), applied=applied_migration.applied, **options))
            else:
                print(format_migration_list_item(migration.name(), applied=False, **options))
        print()

def show_migration_changes(apps):
    """
    Prints a list of all available migrations, and which ones are currently applied.
    Accepts a list of Migrations instances.

    Much simpler, less clear, and much less robust version:
        grep "ing " migrations/*.py
    """
    for app in apps:
        print(app.app_label())
        # Get the migrations objects
        migrations = [migration for migration in app]
        # we use reduce to compare models in pairs, not to generate a value
        reduce(diff_migrations, migrations)

def format_migration_list_item(name, applied=True, **options):
    if applied:
        if int(options.get('verbosity')) >= 2:
            return '  (*) %-80s  (applied %s)' % (name, applied)
        else:
            return '  (*) %s' % name
    else:
        return '  ( ) %s' % name

def diff_migrations(migration1, migration2):

    def model_name(models, model):
        return models[model].get('Meta', {}).get('object_name', model)

    def field_name(models, model, field):
        return '%s.%s' % (model_name(models, model), field)

    print("  " + migration2.name())

    models1 = migration1.migration_class().models
    models2 = migration2.migration_class().models

    # find new models
    for model in models2.keys():
        if not model in models1.keys():
            print('    added model %s' % model_name(models2, model))

    # find removed models
    for model in models1.keys():
        if not model in models2.keys():
            print('    removed model %s' % model_name(models1, model))

    # compare models
    for model in models1:
        if model in models2:

            # find added fields
            for field in models2[model]:
                if not field in models1[model]:
                    print('    added field %s' % field_name(models2, model, field))

            # find removed fields
            for field in models1[model]:
                if not field in models2[model]:
                    print('    removed field %s' % field_name(models1, model, field))

            # compare fields
            for field in models1[model]:
                if field in models2[model]:

                    name = field_name(models1, model, field)

                    # compare field attributes
                    field_value1 = models1[model][field]
                    field_value2 = models2[model][field]

                    # if a field has become a class, or vice versa
                    if type(field_value1) != type(field_value2):
                        print('    type of %s changed from %s to %s' % (
                            name, field_value1, field_value2))

                    # if class
                    elif isinstance(field_value1, dict):
                        # print '    %s is a class' % name
                        pass

                    # else regular field
                    else:

                        type1, attr_list1, field_attrs1 = models1[model][field]
                        type2, attr_list2, field_attrs2 = models2[model][field]

                        if type1 != type2:
                            print('    %s type changed from %s to %s' % (
                                name, type1, type2))

                        if attr_list1 != []:
                            print('    %s list %s is not []' % (
                                name, attr_list1))
                        if attr_list2 != []:
                            print('    %s list %s is not []' % (
                                name, attr_list2))
                        if attr_list1 != attr_list2:
                            print('    %s list changed from %s to %s' % (
                                name, attr_list1, attr_list2))

                        # find added field attributes
                        for attr in field_attrs2:
                            if not attr in field_attrs1:
                                print('    added %s attribute %s=%s' % (
                                    name, attr, field_attrs2[attr]))

                        # find removed field attributes
                        for attr in field_attrs1:
                            if not attr in field_attrs2:
                                print('    removed attribute %s(%s=%s)' % (
                                    name, attr, field_attrs1[attr]))

                        # compare field attributes
                        for attr in field_attrs1:
                            if attr in field_attrs2:

                                value1 = field_attrs1[attr]
                                value2 = field_attrs2[attr]
                                if value1 != value2:
                                    print('    %s attribute %s changed from %s to %s' % (
                                        name, attr, value1, value2))

    return migration2
