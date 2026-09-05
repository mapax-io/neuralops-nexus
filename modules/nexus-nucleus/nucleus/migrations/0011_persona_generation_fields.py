"""
Add the generation settings to Persona.

temperature and max_tokens move off AIModel because they are per-CALL
choices, not properties of the endpoint: two personas sharing one API key
routinely want different settings, which was impossible while these lived
on the model row. (context_window stays on ModelConfig -- that one is a
fact about the model, not a choice.)

max_steps comes from AIAgent, which is being deleted. It has never actually
worked: the runner reads `getattr(persona, "max_steps", None) or
DEFAULT_MAX_ROUNDS` against a config object that carries no such field, so
every run silently used 10 regardless of what was configured.

These land BEFORE 0013 strips temperature/max_tokens from the model row --
0012 copies the existing values across in between. Reversing that order
would lose them.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nucleus', '0010_mcpserver_project_finalize'),
    ]

    operations = [
        migrations.AddField(
            model_name='persona',
            name='temperature',
            field=models.FloatField(default=0.7),
        ),
        migrations.AddField(
            model_name='persona',
            name='max_tokens',
            field=models.PositiveIntegerField(default=4096),
        ),
        migrations.AddField(
            model_name='persona',
            name='max_steps',
            field=models.PositiveIntegerField(
                default=10,
                help_text=(
                    'Maximum agent rounds (tool-call iterations) per trigger. Was '
                    'AIAgent.max_steps, which the runner never actually read -- it '
                    'looked the attribute up on a config object that did not carry '
                    'it, so every run silently used the default.'
                ),
            ),
        ),
    ]
