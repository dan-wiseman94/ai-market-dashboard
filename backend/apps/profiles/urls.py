from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers as nested_routers

from . import views

router = DefaultRouter()
router.register("watchlists", views.WatchlistViewSet, basename="watchlist")
router.register("profiles", views.TradingProfileViewSet, basename="profile")
router.register("presets", views.AgentPresetViewSet, basename="preset")

symbols_router = nested_routers.NestedDefaultRouter(router, "watchlists", lookup="watchlist")
symbols_router.register("symbols", views.WatchlistSymbolViewSet, basename="watchlist-symbols")

urlpatterns = [
    path("", include(router.urls)),
    path("", include(symbols_router.urls)),
]
