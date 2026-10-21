# Smart router bench (owner's ruling 2026-10-20: "no round robin, the router
# will select … based on pros and cons of every model").
#
# The deep seat becomes a BENCH: 0..N ordered models (PersonaDeepModel,
# mirroring PersonaFallbackModel). The router reads each bench model's
# routing_notes (added in 0037) and names its pick; the first bench row is
# the default. The old single Persona.deep_model FK STAYS as a legacy mirror
# of the bench's first entry — services keep it synced so an older engine
# image (which reads PersonaInternal.deep_model) keeps working. The data
# step below seeds the bench from any deep seat already set, so nothing a
# user configured is lost by upgrading.

import django.db.models.deletion
from django.db import migrations, models


def seed_bench_from_single_seat(apps, schema_editor):
    """Every persona with a deep_model gets a one-row bench (position 0)."""
    Persona = apps.get_model("nucleus", "Persona")
    PersonaDeepModel = apps.get_model("nucleus", "PersonaDeepModel")
    rows = [
        PersonaDeepModel(persona_id=p.id, model_id=p.deep_model_id, position=0)
        for p in Persona.objects.filter(deep_model__isnull=False).only("id", "deep_model_id")
    ]
    PersonaDeepModel.objects.bulk_create(rows)


def unseed_bench(apps, schema_editor):
    """Reverse: the single FK still holds the first pick; just drop the rows."""
    apps.get_model("nucleus", "PersonaDeepModel").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("nucleus", "0037_model_generation"),
    ]

    operations = [
        migrations.CreateModel(
            name="PersonaDeepModel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.PositiveSmallIntegerField()),
                ("model", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="deep_links", to="nucleus.modelconfig")),
                ("persona", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="deep_links", to="nucleus.persona")),
            ],
            options={
                "db_table": "intelligence_persona_deep_model",
                "ordering": ["position"],
            },
        ),
        migrations.AddField(
            model_name="persona",
            name="deep_models",
            field=models.ManyToManyField(blank=True, related_name="deep_bench_personas", through="nucleus.PersonaDeepModel", to="nucleus.modelconfig"),
        ),
        migrations.AlterField(
            model_name="persona",
            name="deep_model",
            field=models.ForeignKey(blank=True, help_text="LEGACY mirror of the deep bench's first model — read deep_models instead.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="deep_personas", to="nucleus.modelconfig"),
        ),
        migrations.AddConstraint(
            model_name="personadeepmodel",
            constraint=models.UniqueConstraint(fields=("persona", "model"), name="uniq_persona_deep_model"),
        ),
        migrations.AddConstraint(
            model_name="personadeepmodel",
            constraint=models.UniqueConstraint(fields=("persona", "position"), name="uniq_persona_deep_position"),
        ),
        migrations.RunPython(seed_bench_from_single_seat, unseed_bench),
    ]
