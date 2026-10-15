"""
Step 1 of the nucleus revamp (docs/NUCLEUS-REVAMP.md, 2026-10-14): the money
tables — usage_record (one row per model call, engine contract = handoff
change 1) and usage_model_price (the refreshed price catalog) — plus the three
admin price-override columns on ModelConfig.
"""
import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nucleus", "0029_step0_kill_list"),
    ]

    operations = [
        migrations.CreateModel(
            name="ModelPrice",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("provider", models.CharField(db_index=True, max_length=50)),
                ("model_id", models.CharField(db_index=True, max_length=255)),
                ("input_per_million", models.DecimalField(blank=True, decimal_places=6, max_digits=12, null=True)),
                ("cached_per_million", models.DecimalField(blank=True, decimal_places=6, max_digits=12, null=True)),
                ("output_per_million", models.DecimalField(blank=True, decimal_places=6, max_digits=12, null=True)),
                ("source", models.CharField(default="catalog", help_text="Where this row came from, e.g. the online catalog's name.", max_length=100)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "usage_model_price"},
        ),
        migrations.AddConstraint(
            model_name="modelprice",
            constraint=models.UniqueConstraint(fields=("provider", "model_id"), name="uniq_price_per_provider_model"),
        ),
        migrations.CreateModel(
            name="UsageRecord",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("company_id", models.CharField(db_index=True, max_length=64)),
                ("project_id", models.CharField(db_index=True, max_length=64)),
                ("topic_id", models.CharField(db_index=True, max_length=64)),
                ("persona_id", models.CharField(db_index=True, max_length=64)),
                ("user_id", models.CharField(blank=True, default="", max_length=64)),
                ("message_id", models.CharField(db_index=True, max_length=128)),
                ("job_id", models.CharField(blank=True, default="", max_length=128)),
                ("kind", models.CharField(db_index=True, max_length=32)),
                ("model_config_id", models.CharField(blank=True, default="", max_length=64)),
                ("provider", models.CharField(max_length=50)),
                ("model_id", models.CharField(max_length=255)),
                ("role", models.CharField(blank=True, default="", max_length=20)),
                ("provider_response_id", models.CharField(blank=True, max_length=255, null=True)),
                ("source", models.CharField(blank=True, max_length=50, null=True)),
                ("input_tokens", models.BigIntegerField(default=0)),
                ("uncached_input_tokens", models.BigIntegerField(default=0)),
                ("cache_read_tokens", models.BigIntegerField(default=0)),
                ("cache_write_5m_tokens", models.BigIntegerField(default=0)),
                ("cache_write_1h_tokens", models.BigIntegerField(default=0)),
                ("output_tokens", models.BigIntegerField(default=0)),
                ("reasoning_tokens", models.BigIntegerField(default=0)),
                ("finish_reason", models.CharField(blank=True, max_length=50, null=True)),
                ("estimated", models.BooleanField(default=False)),
                ("cost", models.DecimalField(blank=True, decimal_places=8, max_digits=14, null=True)),
                ("prices_used", models.JSONField(blank=True, null=True)),
                ("price_source", models.CharField(blank=True, default="", help_text="override (admin-typed) | catalog | '' (no price known — cost null)", max_length=20)),
                ("called_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"db_table": "usage_record"},
        ),
        migrations.AddIndex(
            model_name="usagerecord",
            index=models.Index(fields=["company_id", "created_at"], name="usage_rec_company_created_idx"),
        ),
        migrations.AddIndex(
            model_name="usagerecord",
            index=models.Index(fields=["project_id", "created_at"], name="usage_rec_project_created_idx"),
        ),
        migrations.AddIndex(
            model_name="usagerecord",
            index=models.Index(fields=["topic_id", "created_at"], name="usage_rec_topic_created_idx"),
        ),
        migrations.AddIndex(
            model_name="usagerecord",
            index=models.Index(fields=["persona_id", "created_at"], name="usage_rec_persona_created_idx"),
        ),
        migrations.AddIndex(
            model_name="usagerecord",
            index=models.Index(fields=["company_id", "kind"], name="usage_rec_company_kind_idx"),
        ),
        migrations.AddField(
            model_name="modelconfig",
            name="price_input_per_million",
            field=models.DecimalField(blank=True, decimal_places=6, help_text="Override: USD per 1M input tokens. Blank = catalog.", max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name="modelconfig",
            name="price_cached_per_million",
            field=models.DecimalField(blank=True, decimal_places=6, help_text="Override: USD per 1M cached (cache-read) tokens. Blank = catalog.", max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name="modelconfig",
            name="price_output_per_million",
            field=models.DecimalField(blank=True, decimal_places=6, help_text="Override: USD per 1M output tokens. Blank = catalog.", max_digits=12, null=True),
        ),
    ]
