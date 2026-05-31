from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("positions", views.PositionViewSet, basename="position")

urlpatterns = router.urls
