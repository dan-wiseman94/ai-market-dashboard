from rest_framework.routers import DefaultRouter

from apps.files.views import UserFileViewSet

router = DefaultRouter()
router.register(r"", UserFileViewSet, basename="userfile")
urlpatterns = router.urls
