import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser

from .base import BaseModel
from django.conf import settings
from django.core.exceptions import ValidationError

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

    def __str__(self):
        return self.username

    # def clean(self):
    #     super().clean()
    #     if self.user_type == self.UserType.HUMAN:
    #         if not hasattr(self, "human_profile"):
    #             raise ValidationError("Human user must have Human profile")
    #     if self.user_type == self.UserType.PERSONA:
    #         if not hasattr(self, "persona_profile"):
    #             raise ValidationError("Persona user must have Persona profile")

class Human(BaseModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="human_profile",
    )

    full_name = models.CharField(max_length=255)

    email = models.EmailField(
        unique=True,
        db_index=True,
    )

    avatar = models.ImageField(
        upload_to="avatars/%Y/%m/",
        null=True,
        blank=True,
    )

    timezone = models.CharField(max_length=64, default="UTC")
    locale = models.CharField(max_length=20, default="en")

    phone_number = models.CharField(max_length=30, null=True, blank=True)

    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "accounts_human"

    def __str__(self):
        return self.full_name