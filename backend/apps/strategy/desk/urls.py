from rest_framework.routers import DefaultRouter

from apps.strategy.desk.views import DeskViewSet

router = DefaultRouter()
router.register("", DeskViewSet, basename="desk")
urlpatterns = router.urls
