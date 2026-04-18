from rest_framework.routers import DefaultRouter

from apps.backups.views import BackupViewSet

router = DefaultRouter()
router.register("", BackupViewSet, basename="backups")

urlpatterns = router.urls
