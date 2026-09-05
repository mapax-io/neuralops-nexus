"""
Give Persona the two relations that let it absorb AIAgent.

advisor_model -- optional second ModelConfig, exposed to the primary model
as pydantic-ai-harness's Advisor capability ("a second opinion from another
model when stuck"). A capability the model invokes on demand, not a
pipeline stage this backend orchestrates: nucleus only names the row and
ships its credentials. Nullable, because zero-or-one.

mcp_servers -- the M2M that replaces AIAgent.mcp_server, which was a single
FK. The consumer side has always been ready for a list: PersonaConfig.
mcp_servers is a list[MCPServerConfig] and _build_mcp_servers() already
loops, prefixing tool names per server so two servers exposing read_file
do not collide. That code has simply never run with more than one entry.

Both land before the backfill in 0016, which needs mcp_servers to exist in
order to move agent.mcp_server across.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nucleus', '0014_modelconfig_provider_split'),
    ]

    operations = [
        migrations.AddField(
            model_name='persona',
            name='advisor_model',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='advisor_personas',
                to='nucleus.modelconfig',
                help_text=(
                    'Optional second model, exposed to the primary as the Advisor '
                    'capability -- a second opinion when it gets stuck.'
                ),
            ),
        ),
        migrations.AddField(
            model_name='persona',
            name='mcp_servers',
            field=models.ManyToManyField(
                blank=True,
                related_name='personas',
                to='nucleus.mcpserver',
                help_text=(
                    "Tool servers this persona mounts. Zero or more. Every attached "
                    "server must belong to this persona's project -- enforced in "
                    "intelligence/services.py, since Django cannot express a "
                    "cross-FK constraint like that in the database."
                ),
            ),
        ),
    ]
