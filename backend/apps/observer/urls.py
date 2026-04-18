from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("schedules", views.ObserverScheduleViewSet, basename="observer-schedule")
router.register("notifications", views.NotificationViewSet, basename="notification")

urlpatterns = [
    *router.urls,
    path("market-status/", views.market_status_view, name="market-status"),
    path("threads/<int:profile_id>/", views.observer_thread_view, name="observer-thread"),
]
