from django.urls import path
from ninja import NinjaAPI

from authn.api import router as authn_router
from workspace.api import router as workspace_router, members_router
from chat.api import router as chat_router
from intelligence.api import router as intelligence_router
from internal.api import router as internal_router


api = NinjaAPI(
    title="NeuralOps Nucleus API",
    version="1.0.0",
)

api.add_router("/auth/", authn_router)
api.add_router("/members/", members_router)
api.add_router("/projects/", workspace_router)
api.add_router("/projects/", chat_router)
api.add_router("/", intelligence_router)
api.add_router("/internal/", internal_router)

urlpatterns = [
    path("", api.urls),
]
