"""
Step 3 of 3: make MCPServer.project NOT NULL, drop the M2M, and add the
constraint the M2M made impossible.

The old Meta carried this note:

    "no per-company name-uniqueness constraint -- Django can't express
     uniqueness across an M2M's through-table. Per-project collision is
     checked in application code (create_mcp_server_standalone) instead."

With a plain FK that limitation is gone, so uniq_mcp_server_name_per_project
goes in and the manual check comes out of the service layer.

Also drops secret_ref, which no code path ever read -- credentials live in
secrets_encrypted.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nucleus', '0009_mcpserver_project_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='mcpserver',
            name='project',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='mcp_servers',
                to='nucleus.project',
                help_text='The single project this MCP server belongs to. Not transferable.',
            ),
        ),
        migrations.RemoveField(model_name='mcpserver', name='projects'),
        migrations.RemoveField(model_name='mcpserver', name='secret_ref'),
        migrations.AddIndex(
            model_name='mcpserver',
            index=models.Index(fields=['project', 'is_active'], name='intelligenc_project_7837b3_idx'),
        ),
        migrations.AddConstraint(
            model_name='mcpserver',
            constraint=models.UniqueConstraint(
                fields=('project', 'name'), name='uniq_mcp_server_name_per_project'
            ),
        ),
    ]
