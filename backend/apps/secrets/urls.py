from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("providers", views.ProviderConfigViewSet, basename="provider-config")

app_name = "secrets_app"

urlpatterns = [
    path("authorize/", views.schwab_authorize, name="authorize"),
    path("callback/", views.schwab_callback, name="callback"),
    path("status/", views.schwab_status, name="status"),
    path("models/", views.ai_models, name="ai-models"),
    path("usage/", views.ai_usage, name="ai-usage"),
] + router.urls
