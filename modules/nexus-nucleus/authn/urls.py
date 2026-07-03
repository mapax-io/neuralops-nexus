from django.urls import path
from ninja import NinjaAPI

from authn.api import router as authn_router
from authn.members_api import router as members_router
from authn.workspace_api import router as workspace_router
from authn.team_api import router as team_router


api = NinjaAPI(
    title="NeuralOps Nucleus API",
    version="1.0.0",
)

api.add_router("/auth/", authn_router)
api.add_router("/members/", members_router)
api.add_router("/projects/", workspace_router)
api.add_router("/projects/", team_router)   # team endpoints: /{project_id}/team/*

urlpatterns = [
    path("", api.urls),
]
