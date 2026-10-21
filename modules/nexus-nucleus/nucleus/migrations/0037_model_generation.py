# 7b (owner's ruling 2026-10-20, docs/MISSING.md): generation settings move
# to the MODEL card — max_output_tokens + temperature — plus routing_notes,
# the strengths/weaknesses line the smart router reads when choosing a
# hand-over target (same ruling thread).
#
# NO backfill from personas on purpose: several personas can share one
# config with different values, so any copy would be a guess. New fields
# start at the sane defaults (16000 / 0.7); an admin tunes a card once
# (e.g. deepseek-chat's output ceiling is 8K — type 8000 there).
# Persona.temperature/max_tokens columns STAY for now (dropping them is a
# later cleanup once nothing reads them) — the engine stops reading them
# the moment the internal API ships the per-model numbers.
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nucleus", "0036_chains"),
    ]

    operations = [
        migrations.AddField(
            model_name="modelconfig",
            name="max_output_tokens",
            field=models.PositiveIntegerField(
                default=16000,
                help_text="The most this model writes in one reply; its provider's own ceiling still applies.",
            ),
        ),
        migrations.AddField(
            model_name="modelconfig",
            name="temperature",
            field=models.FloatField(
                default=0.7,
                help_text="0 = steady and repeatable, higher = more varied.",
            ),
        ),
        migrations.AddField(
            model_name="modelconfig",
            name="routing_notes",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Short strengths/weaknesses note, e.g. 'best for code, expensive'. The router reads this to pick.",
                max_length=300,
            ),
        ),
    ]
