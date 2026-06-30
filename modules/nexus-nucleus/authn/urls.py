from django.urls import path
from ninja import NinjaAPI

from authn.api import router as authn_router
from authn.members_api import router as members_router


api = NinjaAPI(
    title="NeuralOps Nucleus API",
    version="1.0.0",
)

api.add_router("/auth/", authn_router)
api.add_router("/members/", members_router)

urlpatterns = [
    path("", api.urls),
]
