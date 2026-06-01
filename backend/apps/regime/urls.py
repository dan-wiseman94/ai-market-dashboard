from rest_framework.routers import DefaultRouter

from apps.regime.views import RegimeViewSet

router = DefaultRouter()
router.register("", RegimeViewSet, basename="regime")
urlpatterns = router.urls
