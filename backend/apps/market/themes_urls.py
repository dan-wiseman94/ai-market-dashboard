from rest_framework.routers import DefaultRouter

from apps.market.theme_views import ThemeViewSet

router = DefaultRouter()
router.register("", ThemeViewSet, basename="theme")

urlpatterns = router.urls
