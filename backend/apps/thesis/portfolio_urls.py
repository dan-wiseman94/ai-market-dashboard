"""URLConf for manual position tracking (/api/portfolio/positions/).

Position moved into apps.thesis (the broker-position leg of the thesis loop) per the
27→12 consolidation; the /api/portfolio/ path is unchanged (no OpenAPI drift).
"""

from rest_framework.routers import DefaultRouter

from apps.thesis.portfolio_views import PositionViewSet

router = DefaultRouter()
router.register("positions", PositionViewSet, basename="position")
urlpatterns = router.urls
