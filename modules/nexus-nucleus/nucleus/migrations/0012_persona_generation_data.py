"""
Copy each persona's generation settings off the model row it was using,
BEFORE 0013 drops those columns.

Source depends on how the persona was backed:
    source_type='model'  ->  persona.model.temperature / .max_tokens
    source_type='agent'  ->  persona.agent.model.temperature / .max_tokens
                             plus persona.agent.max_steps

A persona with no resolvable model keeps the field defaults (0.7 / 4096 /
10). It is not an error here -- 0016 is where a persona without a model
becomes a problem, and it reports those properly.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    Persona = apps.get_model('nucleus', 'Persona')
    AIModel = apps.get_model('nucleus', 'AIModel')
    AIAgent = apps.get_model('nucleus', 'AIAgent')

    copied = 0
    for persona in Persona.objects.all().iterator():
        source_model_id = None
        agent = None

        if persona.agent_id:
            agent = AIAgent.objects.filter(pk=persona.agent_id).first()
            if agent is not None:
                source_model_id = agent.model_id
        if source_model_id is None:
            source_model_id = persona.model_id

        fields = []
        if source_model_id:
            model = AIModel.objects.filter(pk=source_model_id).first()
            if model is not None:
                persona.temperature = model.temperature
                persona.max_tokens = model.max_tokens
                fields += ['temperature', 'max_tokens']

        if agent is not None and agent.max_steps:
            persona.max_steps = agent.max_steps
            fields.append('max_steps')

        if fields:
            persona.save(update_fields=fields)
            copied += 1

    print("[0012] carried generation settings onto %d persona row(s)" % copied)


def backwards(apps, schema_editor):
    """No-op: the values still exist on the model rows until 0013 runs."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('nucleus', '0011_persona_generation_fields'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
