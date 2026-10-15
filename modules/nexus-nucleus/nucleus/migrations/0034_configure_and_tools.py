# Step 6 (docs/NUCLEUS-REVAMP.md) — schema half: the configure flag (change
# 13.3) + the stored MCP tool lists (change 6). The backfill that creates a
# configure topic in every EXISTING project lives in 0035 — adding an indexed
# column and inserting rows into the same table in ONE migration trips
# postgres ("cannot CREATE INDEX … pending trigger events": the deferred
# index DDL collides with the inserts' deferred FK checks in one transaction;
# found live, 2026-10-15).
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nucleus", "0033_gateway_tokens"),
    ]

    operations = [
        migrations.AddField(
            model_name="chattopic",
            name="is_configure",
            field=models.BooleanField(default=False, db_index=True),
        ),
        migrations.AddField(
            model_name="mcpserver",
            name="tools",
            field=models.JSONField(blank=True, default=list, help_text="Stored tool list [{name, description, read_only}] — see the Refresh tools button."),
        ),
    ]
