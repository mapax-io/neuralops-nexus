import uuid
from django.db import models

# DeviceSession (device-activation polling) was removed — see
# migrations/0003_delete_devicesession.py. The frontend never used the
# /auth/init/ + /auth/status/ flow; it signs in via Supabase directly.


class OwnerReservation(models.Model):
    """
    Holds a pending owner reservation for demo servers (Task 2.1).
    When someone connects whose verified email matches this reservation,
    they become the owner of the server via claim_install, and this row is deleted.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "authn_owner_reservation"

    def __str__(self):
        return f"OwnerReservation({self.email})"


# ── Permission system bridge ─────────────────────────────────────────────────
# The actual Role / Right / RoleRight / RoleAssignment model classes live in
# authn/permissions/models.py (kept together with the rest of the permission
# system code, see authn/permissions/__init__.py). Django's migration
# autodetector only scans the `authn.models` module for this app, so they're
# re-exported here — this import is the only thing tying them to this file.
from authn.permissions.models import (  # noqa: E402,F401
    ScopeType, ObjectType, Right, Role, RoleRight, RoleAssignment,
)

