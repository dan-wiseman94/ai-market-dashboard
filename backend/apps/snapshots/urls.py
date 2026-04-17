from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("snapshots", views.SnapshotViewSet, basename="snapshot")

urlpatterns = router.urls
