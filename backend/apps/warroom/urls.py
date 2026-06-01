from rest_framework.routers import DefaultRouter

from apps.warroom.views import WarRoomViewSet

router = DefaultRouter()
router.register("runs", WarRoomViewSet, basename="warroom-run")
urlpatterns = router.urls
