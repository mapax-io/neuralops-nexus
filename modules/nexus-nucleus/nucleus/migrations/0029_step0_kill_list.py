"""
Step 0 of the nucleus revamp (docs/NUCLEUS-REVAMP.md, 2026-10-14): drop the
fifteen dead tables. Each was verified dead before deletion — zero code
references outside its own model definition (the audit table in
NUCLEUS-REVAMP.md Step 0 records the proof). Deletion order: FK dependents
first (KnowledgeChunk → KnowledgeFile → KnowledgeBase; UploadPart → Upload).
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("nucleus", "0028_deliverable"),
    ]

    operations = [
        migrations.DeleteModel(name="KnowledgeChunk"),
        migrations.DeleteModel(name="KnowledgeFile"),
        migrations.DeleteModel(name="KnowledgeBase"),
        migrations.DeleteModel(name="UploadPart"),
        migrations.DeleteModel(name="Upload"),
        migrations.DeleteModel(name="EmbeddingJob"),
        migrations.DeleteModel(name="VectorDocument"),
        migrations.DeleteModel(name="ProjectContext"),
        migrations.DeleteModel(name="AuditEvent"),
        migrations.DeleteModel(name="Notification"),
        migrations.DeleteModel(name="UserSession"),
        migrations.DeleteModel(name="SavedSearch"),
        migrations.DeleteModel(name="SearchLog"),
        migrations.DeleteModel(name="ChatReaction"),
        migrations.DeleteModel(name="ChatAttachment"),
    ]
