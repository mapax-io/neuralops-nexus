# Catalog-known model sizes (owner's ruling 2026-10-21: the register dialog's
# context-window / max-output defaults come from a DB the daily price-catalog
# refresh updates — not from a hardcoded frontend table). Two nullable columns
# on ModelPrice; the next refresh_model_prices run fills them.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nucleus", "0040_spend_limit"),
    ]

    operations = [
        migrations.AddField(
            model_name="modelprice",
            name="context_window",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="modelprice",
            name="max_output_tokens",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
