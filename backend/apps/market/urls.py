from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

app_name = "market"

router = DefaultRouter()
router.register("calendar-overrides", views.CalendarOverrideViewSet, basename="calendar-override")

urlpatterns = [
    path("quotes/", views.quotes, name="quotes"),
    path("ohlc/", views.ohlc, name="ohlc"),
    path("positions/", views.positions, name="positions"),
    path("context/", views.context, name="context"),
    path("chain/", views.chain, name="chain"),
    path("news/", views.news, name="news"),
    path("events/", views.events, name="events"),
    path("calendar-status/", views.calendar_status, name="calendar-status"),
    *router.urls,
]
