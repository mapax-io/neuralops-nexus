"""
0007 — rights cleanup for the owner's removal ruling (2026-10-22): Recall
(W5) and Deliverables (W10) left the product (nucleus migration 0042), so
their rights go too. Same pattern as 0005's agent.* cleanup: dropping a code
from the REGISTRY alone would leave it granted in the database forever,
because seed_permissions only ever create-or-updates.
"""
from django.db import migrations

REMOVED = ("recall.manage", "deliverable.manage")


def drop_rights(apps, schema_editor):
    Right = apps.get_model("authn", "Right")
    RoleRight = apps.get_model("authn", "RoleRight")
    RoleRight.objects.filter(right__code__in=REMOVED).delete()
    Right.objects.filter(code__in=REMOVED).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("authn", "0006_team_ops_object_types"),
    ]

    operations = [
        migrations.RunPython(drop_rights, migrations.RunPython.noop),
    ]
