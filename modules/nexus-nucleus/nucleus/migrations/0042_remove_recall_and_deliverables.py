"""
0042 — the owner's removal ruling (2026-10-22, "remove every install from
front or backend" + "remove recallentry completely"): the whole Recall
feature (W5) and the whole Deliverables feature (W10) leave the product.

Drops intelligence_recall_entry, workspace_deliverable (ROWS INCLUDED — the
owner ruled the features out entirely, their data goes with them), and the
persona's recall_enabled column.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nucleus", "0041_catalog_windows"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="persona",
            name="recall_enabled",
        ),
        migrations.DeleteModel(
            name="RecallEntry",
        ),
        migrations.DeleteModel(
            name="Deliverable",
        ),
    ]
