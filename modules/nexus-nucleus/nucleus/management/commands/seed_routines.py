"""
Seed the built-in routines into every active project. Idempotent by name:
a project that already has a built-in keeps it as it is. New projects get
theirs on creation; run this once after upgrading to a server that ships
routines.
"""
from django.core.management.base import BaseCommand

from intelligence.services import seed_builtin_routines
from nucleus.models import Project


class Command(BaseCommand):
    help = "Seed the built-in routines into every active project (idempotent)."

    def handle(self, *args, **options):
        projects = Project.objects.filter(is_active=True)
        total = 0
        for project in projects:
            before = project.routine_items.filter(is_active=True).count()
            seed_builtin_routines(project)
            total += project.routine_items.filter(is_active=True).count() - before
        self.stdout.write(f"{projects.count()} project(s) checked, {total} routine(s) added.")
