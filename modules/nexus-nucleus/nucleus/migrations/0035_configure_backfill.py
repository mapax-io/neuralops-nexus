# Step 6 (docs/NUCLEUS-REVAMP.md) — data half of 0034: every EXISTING active
# project gets its reserved "configure" topic, in its "general" channel (or
# its first channel; a channel is created when a project somehow has none).
# New projects get theirs at creation (workspace/services.create_project).
from django.db import migrations


def make_configure_topics(apps, schema_editor):
    Project = apps.get_model("nucleus", "Project")
    Channel = apps.get_model("nucleus", "Channel")
    ChatTopic = apps.get_model("nucleus", "ChatTopic")

    for project in Project.objects.filter(is_active=True):
        if ChatTopic.objects.filter(project=project, is_configure=True, is_active=True).exists():
            continue
        channel = (
            Channel.objects.filter(project=project, is_active=True, slug="general").first()
            or Channel.objects.filter(project=project, is_active=True).first()
        )
        if channel is None:
            channel = Channel.objects.create(
                company_id=project.company_id, project=project,
                name="general", slug="general", description="General discussion",
            )
        slug = "configure"
        n = 1
        while ChatTopic.objects.filter(channel=channel, slug=slug).exists():
            slug = f"configure-{n}"
            n += 1
        ChatTopic.objects.create(
            company_id=project.company_id, project=project, channel=channel,
            title="configure", slug=slug, is_configure=True,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("nucleus", "0034_configure_and_tools"),
    ]

    operations = [
        migrations.RunPython(make_configure_topics, migrations.RunPython.noop),
    ]
