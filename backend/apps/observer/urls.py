from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("schedules", views.ObserverScheduleViewSet, basename="observer-schedule")

urlpatterns = router.urls
