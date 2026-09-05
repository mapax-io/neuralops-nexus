import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    class UserType(models.TextChoices):
        HUMAN = "human", "Human"
        PERSONA = "persona", "Persona"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user_type = models.CharField(
        max_length=20,
        choices=UserType.choices,
        default=UserType.HUMAN,
        db_index=True,
    )

    google_sso_id = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
    )

    display_name = models.CharField(
        max_length=50,
        blank=True,
        help_text="Per-server display name. Auto-assigned from email on join; editable later.",
        db_index=True,
    )

    avatar = models.ImageField(
        upload_to="avatars/%Y/%m/",
        null=True,
        blank=True,
        help_text=(
            "Shared avatar for both human users and personas (personas via their "
            "identity_user shadow user). Auto-assigned at random from a preset pool "
            "on creation; editable later. See #148."
        ),
    )

    current_company = models.ForeignKey(
        "nucleus.Company",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_active_users",
    )

    class Meta:
        db_table = "accounts_user"
        indexes = [
            models.Index(fields=["user_type"]),
            models.Index(fields=["google_sso_id"]),
        ]

    def get_display_name(self) -> str:
        """Returns display_name if set, otherwise derives from email."""
        if self.display_name:
            return self.display_name
        return (self.email or self.username or "").split("@")[0]

    def get_avatar_url(self) -> str | None:
        """
        Absolute avatar URL (NEURALOPS_SERVER_URL + MEDIA_URL + path), or
        None if unset. Absolute (not MEDIA_URL-relative) on purpose -- the
        frontend renders this directly as an <img src>, with no serverUrl
        prefixing of its own (see #148).
        """
        if not self.avatar:
            return None
        from django.conf import settings
        base = (settings.NEURALOPS_SERVER_URL or "").rstrip("/")
        return f"{base}{self.avatar.url}"

    def __str__(self):
        return self.get_display_name()


# REMOVED: class Human(BaseModel)
#
# The `accounts_human` profile table was never populated. Device-auth users
# only ever got a User row -- see DECISIONS.md §3, which states the rule
# explicitly ("Human profile records are NEVER created for device-auth
# users") and requires _format_member() in workspace/services.py to use
# User.get_display_name() rather than user.human_profile.full_name. Every
# read site already wrapped the lookup in try/except for exactly this
# reason. Dropped in migration 0008.
