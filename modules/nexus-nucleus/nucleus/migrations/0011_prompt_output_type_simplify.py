"""
Simplify OutputType choices to: text, code, html.

Dropped: chart, form — MCP servers pre-render everything to html.
Data migration: chart → html, form → html.
"""
from django.db import migrations, models


def migrate_output_types(apps, schema_editor):
    for model_name in ["Prompt", "PromptTemplate"]:
        Model = apps.get_model("nucleus", model_name)
        Model.objects.filter(output_type="chart").update(output_type="html")
        Model.objects.filter(output_type="form").update(output_type="html")


class Migration(migrations.Migration):

    dependencies = [
        ("nucleus", "0010_aimodel_provider_cleanup"),
    ]

    operations = [
        migrations.RunPython(
            migrate_output_types,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="prompt",
            name="output_type",
            field=models.CharField(
                choices=[
                    ("text", "Text (Markdown)"),
                    ("code", "Code"),
                    ("html", "HTML"),
                ],
                db_index=True,
                default="text",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="prompttemplate",
            name="output_type",
            field=models.CharField(
                choices=[
                    ("text", "Text (Markdown)"),
                    ("code", "Code"),
                    ("html", "HTML"),
                ],
                db_index=True,
                default="text",
                max_length=20,
            ),
        ),
    ]
