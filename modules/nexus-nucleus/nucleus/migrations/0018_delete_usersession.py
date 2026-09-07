# UserSession (provider="supabase", provider_session_id, ip, user agent) was
# never written or read by any code path -- the device-activation flow it
# belonged to was removed with authn/models.py's DeviceSession. Dropped so
# the identity model matches what nucleus actually does with Supabase.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("nucleus", "0017_mcp_internal_capability"),
    ]

    operations = [
        migrations.DeleteModel(name="UserSession"),
    ]
