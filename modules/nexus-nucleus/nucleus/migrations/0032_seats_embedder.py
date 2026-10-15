"""
Step 3 of the nucleus revamp (docs/NUCLEUS-REVAMP.md, 2026-10-14):
- Persona model seats + flags (handoff changes 3 + 7 + 14.6): router_model,
  deep_model, tool_access, approval_scope, delegation_enabled
- CompanyAIConfig.default_router_model (fills an empty router seat at serve time)
- Project.embedder + Project.reindex_status (change 10: per-project embedder,
  locked while its vectors rebuild)
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("nucleus", "0031_paused_runs"),
    ]

    operations = [
        migrations.AddField(
            model_name="persona",
            name="router_model",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="router_personas", to="nucleus.modelconfig",
                help_text="The cheap screening seat. Blank = the company default router, else the engine's fall-through rule.",
            ),
        ),
        migrations.AddField(
            model_name="persona",
            name="deep_model",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="deep_personas", to="nucleus.modelconfig",
                help_text="The escalation seat for hard turns. Blank = no escalation.",
            ),
        ),
        migrations.AddField(
            model_name="persona",
            name="tool_access",
            field=models.CharField(choices=[("all", "All"), ("selected", "Selected")], default="all", max_length=10),
        ),
        migrations.AddField(
            model_name="persona",
            name="approval_scope",
            field=models.CharField(choices=[("topic", "Anyone in the topic"), ("requester_only", "Only the requester")], default="topic", max_length=15),
        ),
        migrations.AddField(
            model_name="persona",
            name="delegation_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="companyaiconfig",
            name="default_router_model",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="+", to="nucleus.modelconfig",
                help_text="Company-wide default router (screening) model for personas without their own.",
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="embedder",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="project",
            name="reindex_status",
            field=models.CharField(blank=True, default="", max_length=10),
        ),
    ]
