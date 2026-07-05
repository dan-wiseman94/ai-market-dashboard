"""URLConf for manual position tracking (/api/portfolio/positions/).

Position is served by apps.thesis (the broker-position leg of the thesis loop)
at the /api/portfolio/ path.
"""

from rest_framework.routers import DefaultRouter

from apps.thesis.portfolio_views import PositionViewSet

router = DefaultRouter()
router.register("positions", PositionViewSet, basename="position")
urlpatterns = router.urls
