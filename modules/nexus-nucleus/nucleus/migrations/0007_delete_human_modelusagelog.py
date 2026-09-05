"""
Drop Human and ModelUsageLog.

Human (accounts_human) was never populated. DECISIONS.md §3 states the rule
explicitly -- "Human profile records are NEVER created for device-auth
users" -- and requires _format_member() in workspace/services.py to use
User.get_display_name() instead. Every read site already wrapped the lookup
in try/except for exactly this reason.

ModelUsageLog had correct FKs to AIModel/User/ChatTopic and a cost_usd
Decimal, clearly intended as the per-model billing table, but ZERO writers
anywhere in the codebase. AIRequestLog took that job, recording
model_id/provider as plain strings rather than foreign keys.

Neither is referenced by any remaining model, so this migration is
independent of everything around it.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('nucleus', '0006_delete_agentapproval_agentrun'),
    ]

    operations = [
        migrations.RemoveField(model_name='human', name='user'),
        migrations.DeleteModel(name='Human'),

        migrations.RemoveField(model_name='modelusagelog', name='company'),
        migrations.RemoveField(model_name='modelusagelog', name='model'),
        migrations.RemoveField(model_name='modelusagelog', name='topic'),
        migrations.RemoveField(model_name='modelusagelog', name='user'),
        migrations.DeleteModel(name='ModelUsageLog'),
    ]
