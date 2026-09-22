"""
Put chat.tasks.reap_orphaned_replies on beat's schedule, every minute.

Beat reads its schedule from the database (CELERY_BEAT_SCHEDULER is the
DatabaseScheduler), so a task the code wants run on a clock is a row, and the
row is created here so every deployment has it after `migrate`. The
PeriodicTasks marker is touched too: the historical models in a migration do
not fire the signal that normally tells beat to reload.
"""
from django.db import migrations
from django.utils import timezone

NAME = "nucleus-reap-orphaned-replies"
TASK = "chat.tasks.reap_orphaned_replies"


def add(apps, schema_editor):
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTasks = apps.get_model("django_celery_beat", "PeriodicTasks")
    every_minute, _ = IntervalSchedule.objects.get_or_create(every=1, period="minutes")
    PeriodicTask.objects.update_or_create(
        name=NAME,
        defaults={"task": TASK, "interval": every_minute, "enabled": True, "one_off": False,
                  "description": "End persona replies the server abandoned mid-run."},
    )
    PeriodicTasks.objects.update_or_create(ident=1, defaults={"last_update": timezone.now()})


def remove(apps, schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(name=NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("nucleus", "0028_deliverable"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]
    operations = [migrations.RunPython(add, remove)]
