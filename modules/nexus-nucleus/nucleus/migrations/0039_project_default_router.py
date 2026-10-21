# The PROJECT-wide default router (owner's ruling 2026-10-19 23:43: the
# default router is a project setting, not a company one). One nullable FK;
# no data step — nothing used the company-wide column it supersedes, so
# there is nothing to carry over.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nucleus", "0038_deep_bench"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="default_router_model",
            field=models.ForeignKey(blank=True, help_text="Fills the router seat of this project's personas that have none of their own.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="nucleus.modelconfig"),
        ),
    ]
