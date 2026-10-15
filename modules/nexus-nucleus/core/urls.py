from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path
from ninja import NinjaAPI

from authn.api import me_router, roles_router, router as authn_router
from workspace.api import router as workspace_router, members_router
from chat.api import router as chat_router, search_router
from intelligence.api import router as intelligence_router
from intelligence.usage_api import router as usage_router, company_router as usage_company_router
from internal.api import router as internal_router
from context.api import router as context_router
from scheduling.api import router as scheduling_router
from scheduling.hooks_api import router as hooks_router
from gateway.api import mcp_router, tokens_router

api = NinjaAPI(
    title="NeuralOps Nucleus API",
    version="1.0.0",
)

api.add_router("/auth/", authn_router)
api.add_router("/me/", me_router)
api.add_router("/roles/", roles_router)
api.add_router("/members/", members_router)
api.add_router("/projects/", workspace_router)
api.add_router("/projects/", chat_router)
api.add_router("/search/", search_router)
api.add_router("/", intelligence_router)
api.add_router("/internal/", internal_router)
api.add_router("/projects/", context_router)
api.add_router("/projects/", scheduling_router)
# Usage reads (Step 1): topic/project under /projects/, the company rollup at /usage/company/.
api.add_router("/projects/", usage_router)
api.add_router("/usage/", usage_company_router)
# Public on purpose (W12): the token in the path is the credential. nginx does
# not block it -- an inbound hook is only useful from outside.
api.add_router("/hooks/", hooks_router)
# Step 6: the MCP gateway (this server as a tool) + its personal tokens.
api.add_router("/mcp", mcp_router)
api.add_router("/gateway/tokens/", tokens_router)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", api.urls),
]

# Serve MEDIA_ROOT (avatars, uploaded attachments, ...) directly — ALWAYS,
# not only under DEBUG (Step 6 posture fix: Step 4 turned DEBUG off in
# production, and django's static() helper refuses to serve when DEBUG is
# false — avatars would 404 behind nginx's /media/ proxy, which points at
# nucleus, not at a shared volume). django.views.static.serve is fine at this
# scale; moving media onto an nginx-served volume is a later optimisation.
from django.views.static import serve as _media_serve  # noqa: E402
from django.urls import re_path  # noqa: E402

urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", _media_serve, {"document_root": settings.MEDIA_ROOT}),
]
