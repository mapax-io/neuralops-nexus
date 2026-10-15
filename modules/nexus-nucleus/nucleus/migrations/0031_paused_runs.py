"""
Step 2 of the nucleus revamp (docs/NUCLEUS-REVAMP.md, 2026-10-14): the parked
runs — chat_paused_run (the engine's pause state + the decisions, consumed on
resume) — and the PAUSED message status (a choices change; no column change).
"""
import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nucleus", "0030_money_tables"),
    ]

    operations = [
        migrations.CreateModel(
            name="PausedRun",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("message_id", models.CharField(db_index=True, max_length=64, unique=True)),
                ("job_id", models.CharField(blank=True, default="", max_length=128)),
                ("topic_id", models.CharField(db_index=True, max_length=64)),
                ("persona_id", models.CharField(blank=True, default="", max_length=64)),
                ("state", models.TextField()),
                ("catalog_hash", models.CharField(blank=True, default="", max_length=128)),
                ("pending", models.JSONField(default=list)),
                ("role", models.CharField(blank=True, default="STANDARD", max_length=20)),
                ("job", models.JSONField(blank=True, default=dict)),
                ("decisions", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"db_table": "chat_paused_run"},
        ),
        migrations.AlterField(
            model_name="chatmessage",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("streaming", "Streaming"),
                    ("completed", "Completed"),
                    ("failed", "Failed"),
                    ("cancelled", "Cancelled"),
                    ("paused", "Paused"),
                ],
                db_index=True,
                default="completed",
                max_length=20,
            ),
        ),
    ]
