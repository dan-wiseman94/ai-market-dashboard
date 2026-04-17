from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("threads", views.ThreadViewSet, basename="thread")

urlpatterns = router.urls
