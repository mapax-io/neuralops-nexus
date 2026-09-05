"""
Retire the agent.* rights and rename ai_model.* -> model_config.*.

This migration is NOT optional housekeeping. `manage.py seed_permissions`
only ever create-or-updates -- it has no delete path -- so removing entries
from rights.py:REGISTRY leaves the old Right rows, and every RoleRight
pointing at them, in the database forever. They would keep being granted to
whoever holds the role, referring to endpoints that no longer exist.

Two things happen here:

  1. agent.list / agent.create / agent.update / agent.delete are deleted,
     along with their RoleRight links. AIAgent is gone -- Persona absorbed
     it -- so there is nothing left for those rights to authorise.

  2. ai_model.* codes are renamed in place, preserving each row's id and
     therefore every RoleRight already pointing at it. Renaming rather than
     delete-and-reseed is what keeps existing grants intact: an Admin who
     could manage AI models yesterday can manage model configs today,
     without anyone re-assigning roles.

object_type and scope and description are deliberately NOT corrected here.
The next `seed_permissions` run does that -- it updates existing rows by
code -- and duplicating the registry's contents inside a migration would
just be a second copy to keep in sync.

Run after this:  manage.py seed_permissions
"""
from django.db import migrations, models


_RENAMES = [
    ("ai_model.list",   "model_config.list"),
    ("ai_model.create", "model_config.create"),
    ("ai_model.delete", "model_config.delete"),
    ("ai_model.attach", "model_config.attach"),
]


def forwards(apps, schema_editor):
    Right = apps.get_model("authn", "Right")
    RoleRight = apps.get_model("authn", "RoleRight")

    dead = Right.objects.filter(code__startswith="agent.")
    dead_codes = list(dead.values_list("code", flat=True))
    unlinked = RoleRight.objects.filter(right__in=dead).delete()[0]
    removed = dead.delete()[0]
    print("[authn.0005] removed %d agent.* right(s) %s and %d role link(s)"
          % (removed, dead_codes, unlinked))

    for old, new in _RENAMES:
        # A row under the new name already existing would mean seed_permissions
        # ran against the new registry before this migration -- in which case
        # the old row is a duplicate with stale grants, so drop it instead.
        if Right.objects.filter(code=new).exists():
            RoleRight.objects.filter(right__code=old).delete()
            Right.objects.filter(code=old).delete()
            continue
        Right.objects.filter(code=old).update(code=new)

    print("[authn.0005] renamed ai_model.* -> model_config.* (grants preserved)")


def backwards(apps, schema_editor):
    """
    Reverses the renames only. The agent.* rights are not restored: their
    RoleRight links are gone and there is no record of which roles held them.
    """
    Right = apps.get_model("authn", "Right")
    for old, new in _RENAMES:
        Right.objects.filter(code=new).update(code=old)


class Migration(migrations.Migration):

    dependencies = [
        ('authn', '0004_alter_right_object_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='right',
            name='object_type',
            field=models.CharField(
                choices=[
                    ('project', 'Project'),
                    ('channel', 'Channel'),
                    ('topic', 'Chat Topic'),
                    ('session', 'Chat Session'),
                    ('persona', 'Persona'),
                    ('mcp_server', 'MCP Server'),
                    ('model_config', 'Model Config'),
                    ('company', 'Company'),
                    ('schedule', 'Persona Schedule'),
                ],
                max_length=20,
            ),
        ),
        migrations.RunPython(forwards, backwards),
    ]
