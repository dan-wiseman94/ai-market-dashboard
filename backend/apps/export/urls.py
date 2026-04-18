from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.export.views import ExportViewSet, export_single_thread

router = DefaultRouter()
router.register("", ExportViewSet, basename="exports")

urlpatterns = [
    path("thread/<int:thread_id>/", export_single_thread, name="export-single-thread"),
] + router.urls
