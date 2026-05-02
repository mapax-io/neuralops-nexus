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

    current_company = models.ForeignKey(
        "governance.Company",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_active_users",
    )

    class Meta:
        db_table = "accounts_user"

    def __str__(self):
        return self.username