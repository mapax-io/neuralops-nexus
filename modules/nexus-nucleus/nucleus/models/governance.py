from django.conf import settings
from django.db import models

from .base import BaseModel


class Company(BaseModel):
    """
    Tenant/company/workspace root.
    """

    name = models.CharField(max_length=255)

    slug = models.SlugField(
        max_length=120,
        unique=True,
    )

    is_personal = models.BooleanField(
        default=False,
        help_text="Whether this is a personal/private workspace.",
    )

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_companies",
        null=True,
        blank=True,
        help_text="The user who owns and administrates this company.",
    )

    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="CompanyAccess",
        through_fields=("company", "user"),
        related_name="companies",
    )

    class Meta:
        db_table = "governance_company"
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return self.name


class CompanyAccess(BaseModel):
    """
    User membership and permissions inside a company.
    """

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"
        VIEWER = "viewer", "Viewer"

    company = models.ForeignKey(
        "nucleus.Company",
        on_delete=models.CASCADE,
        related_name="access_list",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="company_access",
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.MEMBER,
        db_index=True,
    )

    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_invites_sent",
    )

    joined_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        db_table = "governance_company_access"

        constraints = [
            models.UniqueConstraint(
                fields=["company", "user"],
                name="uniq_company_user_access",
            )
        ]

        indexes = [
            models.Index(fields=["company", "role"]),
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self):
        return f"{self.user} -> {self.company} ({self.role})"