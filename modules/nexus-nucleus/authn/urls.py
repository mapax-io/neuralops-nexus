from django.urls import path
from ninja import NinjaAPI

from authn.api import router as authn_router
from authn.members_api import router as members_router
from authn.workspace_api import router as workspace_router
from authn.team_api import router as team_router
from authn.chat_api import router as chat_router
from authn.intelligence_api import router as intelligence_router
from authn.internal_api import router as internal_router
# ⚠️ SPIKE — delete this import when nexus-ai streaming is wired up
from authn.dev_ai_spike import router as dev_spike_router


api = NinjaAPI(
    title="NeuralOps Nucleus API",
    version="1.0.0",
)

api.add_router("/auth/", authn_router)
api.add_router("/members/", members_router)
api.add_router("/projects/", workspace_router)
api.add_router("/projects/", team_router)
api.add_router("/projects/", chat_router)
api.add_router("/", intelligence_router)
api.add_router("/internal/", internal_router)
# ⚠️ SPIKE — delete this line when nexus-ai streaming is wired up
api.add_router("/dev/", dev_spike_router)

urlpatterns = [
    path("", api.urls),
]
