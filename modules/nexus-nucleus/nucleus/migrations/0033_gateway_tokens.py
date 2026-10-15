# Step 6 (docs/NUCLEUS-REVAMP.md) — the gateway's personal tokens.
import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nucleus", "0032_seats_embedder"),
    ]

    operations = [
        migrations.CreateModel(
            name="GatewayToken",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(help_text='What it\'s for ("my laptop", "CI").', max_length=100)),
                ("token_hash", models.CharField(max_length=64, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_gateway_tokens", to="nucleus.user")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="gateway_tokens", to="nucleus.user")),
            ],
            options={
                "db_table": "gateway_token",
                "ordering": ["-created_at"],
            },
        ),
    ]
