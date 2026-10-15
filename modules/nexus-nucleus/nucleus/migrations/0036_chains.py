"""
Step 7 (docs/NUCLEUS-REVAMP.md) — runbooks grow into chains (ruling 1: the
SAME tables, no parallel family).

Runbook gains: supervisor (one optional reviewing persona, ruling 2) and
redo_limit (bounded redo, ruling 3). RunbookRun gains: the WAITING status plus
`checkpoint` (the pending question, ruling 4) and `context` (the last good
output, persisted so a paused run resumes in a fresh Celery task).

SCHEMA ONLY — no RunPython here, following 0034's lesson (schema and data
backfills live in separate migrations on postgres). Nothing needs backfilling:
every new field has a safe default for existing rows.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("nucleus", "0035_configure_backfill"),
    ]

    operations = [
        migrations.AddField(
            model_name="runbook",
            name="supervisor",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="supervised_runbooks", to="nucleus.persona",
            ),
        ),
        migrations.AddField(
            model_name="runbook",
            name="redo_limit",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="runbookrun",
            name="context",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="runbookrun",
            name="checkpoint",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="runbookrun",
            name="status",
            field=models.CharField(
                choices=[
                    ("queued", "Queued"), ("running", "Running"),
                    ("waiting", "Waiting for a person"),
                    ("done", "Done"), ("failed", "Failed"), ("stopped", "Stopped"),
                ],
                db_index=True, default="queued", max_length=12,
            ),
        ),
    ]
