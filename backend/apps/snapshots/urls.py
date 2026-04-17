from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("snapshots", views.SnapshotViewSet, basename="snapshot")

urlpatterns = [
    path("snapshots/images/", views.images_collection, name="snapshot-images"),
    path("snapshots/images/<int:image_id>/", views.serve_image, name="snapshot-image-serve"),
    *router.urls,
]
