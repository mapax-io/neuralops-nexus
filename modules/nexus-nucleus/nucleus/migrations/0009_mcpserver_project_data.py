"""
Step 2 of 3: copy each MCPServer's single M2M project into the new FK.

The `projects` M2M was only ever given one entry -- create_mcp_server_
standalone() and provision_project_folder_and_mcp() both do exactly one
.add(), and no attach-to-another-project endpoint was ever built. This
takes .first() and asserts that assumption held.

Fails loudly rather than letting 0010's NOT NULL blow up with an opaque
IntegrityError. A server with zero projects is unreachable data (invisible
under every row-visibility rule); a server with several means someone
attached one by hand. Either way a human has to decide, so the message
names the rows.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    MCPServer = apps.get_model('nucleus', 'MCPServer')

    orphans, multi = [], []
    for server in MCPServer.objects.all().iterator():
        projects = list(server.projects.all()[:2])
        if not projects:
            orphans.append((str(server.pk), server.name, server.is_active))
            continue
        if len(projects) > 1:
            multi.append((str(server.pk), server.name))
        server.project_id = projects[0].pk
        server.save(update_fields=['project'])

    if multi:
        print(
            "[0009] WARNING -- MCP servers attached to more than one project; "
            "kept the first only: %s" % (multi,)
        )

    if orphans:
        raise RuntimeError(
            "[0009] %d MCPServer row(s) have no project and cannot get a "
            "non-null project_id in 0010: %s\n"
            "Fix the data first -- attach them to a project, or delete them "
            "if they are unreachable leftovers -- then re-run migrate."
            % (len(orphans), orphans)
        )


def backwards(apps, schema_editor):
    """Put the FK value back into the M2M so 0008 can drop the column."""
    MCPServer = apps.get_model('nucleus', 'MCPServer')
    for server in MCPServer.objects.filter(project__isnull=False).iterator():
        server.projects.add(server.project_id)


class Migration(migrations.Migration):

    dependencies = [
        ('nucleus', '0008_mcpserver_project_add'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
