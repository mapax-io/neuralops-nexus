"""
The one that actually collapses the model. Schema, then data, then schema
again -- the ordering is load-bearing in both directions.

FIRST the XOR constraint comes off. persona_model_or_agent_required says:

    (source_type='model' AND model NOT NULL AND agent IS NULL)
 OR (source_type='agent' AND agent NOT NULL AND model IS NULL)

and the backfill's whole job is to set `model` on a persona that still has
source_type='agent' and a non-null `agent` -- which satisfies neither
branch. Leaving the constraint in place until after the data step fails on
the first agent-backed persona with a CheckViolation.

THEN the backfill:
    source_type='model'  ->  `model` is already correct, nothing to do
    source_type='agent'  ->  model = agent.model
                             mcp_servers += {agent.mcp_server}

THEN the rest:
    - drop source_type and agent
    - model -> NOT NULL
    - add persona_advisor_differs_from_model
    - swap index 2088d0 (company, source_type) for 245b73 (model)
    - delete AIAgent

`model` can only become NOT NULL once every persona has one, and `agent`
can only be dropped once nothing needs to read it -- which is why all of
this is one migration rather than three.

After this, "agent-ness" is emergent rather than a record: a persona with
no MCP servers is a plain LLM, one with servers has tools. That is already
how the runner behaves -- _build_mcp_servers() returns [] for none and
falls through to a plain model.
"""
import django.db.models.deletion
from django.db import migrations, models


def forwards(apps, schema_editor):
    Persona = apps.get_model('nucleus', 'Persona')
    AIAgent = apps.get_model('nucleus', 'AIAgent')

    moved, attached, broken = 0, 0, []

    for persona in Persona.objects.filter(agent_id__isnull=False).iterator():
        agent = AIAgent.objects.filter(pk=persona.agent_id).first()
        if agent is None or not agent.model_id:
            broken.append((str(persona.pk), persona.name, persona.is_active))
            continue

        persona.model_id = agent.model_id
        persona.save(update_fields=['model'])
        moved += 1

        if agent.mcp_server_id:
            persona.mcp_servers.add(agent.mcp_server_id)
            attached += 1

    print("[0016] repointed %d agent-backed persona(s); attached %d MCP server(s)"
          % (moved, attached))

    if broken:
        print(
            "[0016] NOTE -- %d persona(s) reference an agent with no model: %s"
            % (len(broken), broken)
        )

    stranded = list(
        Persona.objects.filter(model_id__isnull=True).values_list('pk', 'name', 'is_active')
    )
    if stranded:
        raise RuntimeError(
            "[0016] %d Persona row(s) have no model and cannot satisfy the NOT NULL "
            "below:\n  %s\n"
            "These are usually personas backed by an EXTERNAL agent, which was "
            "allowed to have model=NULL (only internal_agent_requires_model forced "
            "one).\n"
            "Decide per row, then re-run migrate:\n"
            "  assign one -> UPDATE intelligence_persona SET model_id='<modelconfig "
            "uuid>' WHERE id='...';\n"
            "  or discard  -> DELETE FROM intelligence_persona WHERE id='...';"
            % (len(stranded), '\n  '.join(map(str, stranded)))
        )

    # Postgres refuses ALTER TABLE on a relation that has pending deferred-
    # constraint triggers, and everything above queues them: Django declares
    # its foreign keys DEFERRABLE INITIALLY DEFERRED, so the persona UPDATEs
    # and the mcp_servers M2M inserts leave checks scheduled for COMMIT.
    # The RemoveField operations below are ALTER TABLEs in this same
    # transaction, so without this they fail with
    #   "cannot ALTER TABLE ... because it has pending trigger events"
    # Forcing the deferred checks to run now drains that queue -- and if any
    # of them would have failed, it surfaces here, where the error is about
    # the data, rather than as an opaque DDL error further down.
    schema_editor.execute('SET CONSTRAINTS ALL IMMEDIATE')


def backwards(apps, schema_editor):
    """
    Not reversible. AIAgent is dropped below and its rows are gone; there is
    nothing left to reconstruct persona.agent from. Restore from the dump
    taken before this migration ran.
    """
    raise RuntimeError(
        "0016 is forward-only -- AIAgent rows are destroyed. Restore from the "
        "pre-refactor pg_dump instead."
    )


class Migration(migrations.Migration):

    dependencies = [
        ('nucleus', '0015_persona_advisor_and_mcp_servers'),
    ]

    operations = [
        # MUST precede the backfill -- see the module docstring.
        migrations.RemoveConstraint(
            model_name='persona',
            name='persona_model_or_agent_required',
        ),

        migrations.RunPython(forwards, backwards),

        # -- persona: shed the discriminator ----------------------------------
        migrations.RemoveIndex(
            model_name='persona',
            name='intelligenc_company_2088d0_idx',
        ),
        migrations.RemoveField(model_name='persona', name='source_type'),
        migrations.RemoveField(model_name='persona', name='agent'),

        migrations.AlterField(
            model_name='persona',
            name='model',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='personas',
                to='nucleus.modelconfig',
                help_text='The primary model. Required.',
            ),
        ),
        migrations.AddIndex(
            model_name='persona',
            index=models.Index(fields=['model'], name='intelligenc_model_i_245b73_idx'),
        ),
        migrations.AddConstraint(
            model_name='persona',
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ('advisor_model__isnull', True),
                    models.Q(('advisor_model', models.F('model')), _negated=True),
                    _connector='OR',
                ),
                name='persona_advisor_differs_from_model',
            ),
        ),

        # -- AIAgent goes ------------------------------------------------------
        migrations.RemoveField(model_name='aiagent', name='company'),
        migrations.RemoveField(model_name='aiagent', name='mcp_server'),
        migrations.RemoveField(model_name='aiagent', name='model'),
        migrations.RemoveField(model_name='aiagent', name='projects'),
        migrations.DeleteModel(name='AIAgent'),
    ]
