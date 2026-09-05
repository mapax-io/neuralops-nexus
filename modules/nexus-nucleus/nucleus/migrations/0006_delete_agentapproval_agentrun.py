"""
Drop AgentApproval and AgentRun.

Both belong to an approval-gated agent-execution design that was modelled
and never built. Verified unreferenced across every service layer and
mounted API module: no imports, no queries, no schemas, no endpoints, and
no agent_run.* right in authn/permissions/rights.py (ObjectType had no
member for them either). AgentRun.status even carried a "waiting_approval"
value that nothing could set, because the only thing that would have set it
was AgentApproval.

They come out first because AgentRun.agent is an FK into AIAgent, which is
deleted in 0016 -- the table cannot go while a foreign key points at it.

AgentApproval precedes AgentRun: AgentApproval.run CASCADEs off AgentRun.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('nucleus', '0005_remove_aiagent_system_prompt_mcpserver_auth_type_and_more'),
    ]

    operations = [
        migrations.RemoveField(model_name='agentapproval', name='approved_by'),
        migrations.RemoveField(model_name='agentapproval', name='company'),
        migrations.RemoveField(model_name='agentapproval', name='project'),
        migrations.RemoveField(model_name='agentapproval', name='requested_by'),
        migrations.RemoveField(model_name='agentapproval', name='run'),
        migrations.DeleteModel(name='AgentApproval'),

        migrations.RemoveField(model_name='agentrun', name='agent'),
        migrations.RemoveField(model_name='agentrun', name='company'),
        migrations.RemoveField(model_name='agentrun', name='project'),
        migrations.RemoveField(model_name='agentrun', name='topic'),
        migrations.RemoveField(model_name='agentrun', name='triggered_by'),
        migrations.DeleteModel(name='AgentRun'),
    ]
