"""
Step 6 (docs/NUCLEUS-REVAMP.md) — the gateway's personal tokens.

A GatewayToken lets an MCP client (Claude Desktop, Cursor, a persona) use
this NeuralOps server as a tool, acting AS `user` — never more: every tool
call runs through PermissionChecker as that person. The raw token is shown
exactly once at creation; only its sha256 lands here (same rule as the
inbound hooks' tokens). Minting is gated on the `gateway.token` right (the
four roles: company owner/admin, project owner/admin — Step 6 ruling 2);
company-level holders see and revoke every token.
"""
import uuid

from django.db import models


class GatewayToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Who the token ACTS AS — its rights are exactly this person's.
    user = models.ForeignKey(
        "nucleus.User", on_delete=models.CASCADE, related_name="gateway_tokens",
    )
    # Who minted it (an admin can mint for a member); kept for the revoke rule
    # and the audit trail. SET_NULL: the token survives its creator leaving.
    created_by = models.ForeignKey(
        "nucleus.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="created_gateway_tokens",
    )
    name = models.CharField(max_length=100, help_text='What it\'s for ("my laptop", "CI").')
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "gateway_token"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.user_id})"
