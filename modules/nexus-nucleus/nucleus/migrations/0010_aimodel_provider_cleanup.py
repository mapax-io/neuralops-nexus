"""
Collapse AIModel.Provider enum to LITELLM + LOCAL.

Data migration: all existing provider values (openai, anthropic, ollama, azure)
are converted to 'litellm' since they all route through LiteLLM anyway.
The actual provider is encoded in model_id (e.g. 'anthropic/claude-haiku-4-5-20251001').
"""
from django.db import migrations, models


def migrate_providers_to_litellm(apps, schema_editor):
    AIModel = apps.get_model("nucleus", "AIModel")
    legacy_providers = ["openai", "anthropic", "ollama", "azure"]
    AIModel.objects.filter(provider__in=legacy_providers).update(provider="litellm")


class Migration(migrations.Migration):

    dependencies = [
        ("nucleus", "0009_prompt_prompttemplate"),
    ]

    operations = [
        # Step 1: migrate data before tightening choices
        migrations.RunPython(
            migrate_providers_to_litellm,
            reverse_code=migrations.RunPython.noop,
        ),
        # Step 2: update field choices (informational only — not enforced at DB level)
        migrations.AlterField(
            model_name="aimodel",
            name="provider",
            field=models.CharField(
                choices=[
                    ("litellm", "LiteLLM (all cloud/hosted providers)"),
                    ("local", "Local (custom ONNX / llama.cpp runtime)"),
                ],
                db_index=True,
                default="litellm",
                max_length=50,
            ),
        ),
    ]
