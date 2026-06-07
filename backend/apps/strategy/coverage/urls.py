from rest_framework.routers import DefaultRouter

from apps.strategy.coverage.views import CoverageViewSet

router = DefaultRouter()
router.register("", CoverageViewSet, basename="coverage")

urlpatterns = router.urls
