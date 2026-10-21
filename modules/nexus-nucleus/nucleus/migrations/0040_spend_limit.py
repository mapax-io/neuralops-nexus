# The per-project monthly SPEND LIMIT (owner's ruling 2026-10-21: "per-project
# cap, block"). One nullable Decimal column; null = no limit, which is every
# existing project's state, so there is no data step.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nucleus", "0039_project_default_router"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="spend_limit_monthly",
            field=models.DecimalField(blank=True, decimal_places=2, help_text="USD per calendar month; personas here stop answering once the month's estimated spend reaches it.", max_digits=9, null=True),
        ),
    ]
