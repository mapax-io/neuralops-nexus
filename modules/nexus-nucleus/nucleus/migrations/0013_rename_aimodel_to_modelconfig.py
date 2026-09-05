"""
AIModel -> ModelConfig.

RenameModel + AlterModelTable, NOT CreateModel + DeleteModel. This matters:
`makemigrations` did not detect the rename and proposed creating an empty
intelligence_model_config and dropping intelligence_ai_model, which would
have destroyed every model row and every Fernet-encrypted API key with it.
RenameModel preserves the rows, the FKs pointing at them, and the M2M
through-table.

Index names are rebuilt rather than carried over. Django derives an auto
index name from a hash of the table name, so renaming the table changes
what it expects: the old pair (671d7a / 21473e) was computed against
"intelligence_ai_model", the new pair (9310ee / 49dab5) against
"intelligence_model_config". The old names still exist in the database
after the table rename -- Postgres does not rename indexes with their table
-- so they are dropped explicitly here.

Also drops the three fields that do not belong on a credentials row:
  temperature, max_tokens -> moved to Persona (copied across in 0012)
  secret_ref              -> never read by any code path
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nucleus', '0012_persona_generation_data'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameModel(old_name='AIModel', new_name='ModelConfig'),
        migrations.AlterModelTable(
            name='modelconfig',
            table='intelligence_model_config',
        ),

        # -- old constraint / indexes, named for the old table -----------------
        migrations.RemoveConstraint(
            model_name='modelconfig',
            name='uniq_ai_model_name_per_company',
        ),
        migrations.RemoveIndex(
            model_name='modelconfig',
            name='intelligenc_company_671d7a_idx',
        ),
        migrations.RemoveIndex(
            model_name='modelconfig',
            name='intelligenc_company_21473e_idx',
        ),

        # -- fields that leave -------------------------------------------------
        migrations.RemoveField(model_name='modelconfig', name='temperature'),
        migrations.RemoveField(model_name='modelconfig', name='max_tokens'),
        migrations.RemoveField(model_name='modelconfig', name='secret_ref'),

        # -- fields that change ------------------------------------------------
        migrations.AlterField(
            model_name='modelconfig',
            name='name',
            field=models.CharField(
                max_length=255,
                help_text="Human-readable name, e.g. 'Claude Haiku (prod)'.",
            ),
        ),
        migrations.AlterField(
            model_name='modelconfig',
            name='provider',
            field=models.CharField(
                choices=[
                    ('openai', 'OpenAI'),
                    ('anthropic', 'Anthropic'),
                    ('google', 'Google (Gemini)'),
                    ('ollama', 'Ollama (local)'),
                    ('openai_compatible', 'OpenAI-compatible endpoint'),
                ],
                db_index=True,
                default='openai',
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name='modelconfig',
            name='model_id',
            field=models.CharField(
                max_length=255,
                help_text=(
                    "BARE model name -- no provider prefix, no separator. e.g. "
                    "'gpt-4o', 'claude-haiku-4-5-20251001', 'gemini-2.0-flash', "
                    "'llama3'. The 'provider:model' string handed to pydantic-ai "
                    "is composed by qualified_id."
                ),
            ),
        ),
        migrations.AlterField(
            model_name='modelconfig',
            name='api_base',
            field=models.URLField(
                blank=True,
                null=True,
                help_text=(
                    'Custom endpoint. Required for provider=openai_compatible; '
                    'optional for ollama; unused for the native providers unless '
                    'proxying.'
                ),
            ),
        ),
        migrations.AlterField(
            model_name='modelconfig',
            name='supports_tools',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Whether this model can call tools. Load-bearing now: a persona '
                    'may only mount MCP servers on a tool-capable model.'
                ),
            ),
        ),
        migrations.AlterField(
            model_name='modelconfig',
            name='created_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='created_model_configs',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='modelconfig',
            name='projects',
            field=models.ManyToManyField(
                blank=True,
                related_name='model_configs',
                to='nucleus.project',
                help_text=(
                    'Projects this model config is attached to / visible from. Every '
                    'attached project must belong to the same company as this config '
                    '-- enforced in intelligence/services.py, NOT by the database '
                    '(Django cannot constrain an auto-generated M2M through-table).'
                ),
            ),
        ),

        # -- new constraint / indexes, named for the new table -----------------
        migrations.AddIndex(
            model_name='modelconfig',
            index=models.Index(fields=['company', 'provider'], name='intelligenc_company_9310ee_idx'),
        ),
        migrations.AddIndex(
            model_name='modelconfig',
            index=models.Index(fields=['company', 'is_active'], name='intelligenc_company_49dab5_idx'),
        ),
        migrations.AddConstraint(
            model_name='modelconfig',
            constraint=models.UniqueConstraint(
                fields=('company', 'name'), name='uniq_model_config_name_per_company'
            ),
        ),

        # -- CompanyAIConfig default now carries pydantic-ai format -------------
        migrations.AlterField(
            model_name='companyaiconfig',
            name='default_llm_model',
            field=models.CharField(
                max_length=255,
                default='anthropic:claude-haiku-4-5-20251001',
                help_text="Fallback LLM, in pydantic-ai 'provider:model' format.",
            ),
        ),
    ]
