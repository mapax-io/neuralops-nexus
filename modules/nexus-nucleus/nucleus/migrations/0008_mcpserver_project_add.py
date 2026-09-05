"""
Step 1 of 3 converting MCPServer project ownership from M2M to FK.

Adds the `project` column NULLABLE so existing rows survive. 0009 copies
the single M2M entry into it; 0010 makes it NOT NULL, drops the M2M, and
adds the per-project name uniqueness that the M2M made impossible.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('nucleus', '0007_delete_human_modelusagelog'),
    ]

    operations = [
        migrations.AddField(
            model_name='mcpserver',
            name='project',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='mcp_servers',
                to='nucleus.project',
                help_text='The single project this MCP server belongs to. Not transferable.',
            ),
        ),
    ]
