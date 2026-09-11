from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path
from ninja import NinjaAPI

from authn.api import me_router, roles_router, router as authn_router
from workspace.api import router as workspace_router, members_router
from chat.api import router as chat_router
from intelligence.api import router as intelligence_router
from internal.api import router as internal_router
from context.api import router as context_router
from scheduling.api import router as scheduling_router

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
api.add_router("/", intelligence_router)
api.add_router("/internal/", internal_router)
api.add_router("/projects/", context_router)
api.add_router("/projects/", scheduling_router)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", api.urls),
]

# Serve MEDIA_ROOT (avatars, uploaded attachments, ...) directly -- fine for
# dev/staging (DEBUG is always True here per settings.py); swap for real
# static-file hosting (nginx/S3/etc.) before this is ever DEBUG=False. See #148.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
