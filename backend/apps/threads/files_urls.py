"""URLConf for the Anthropic Files API proxy (GET/POST/DELETE /api/files/...).

UserFile is a thread concern (file attachments become document blocks on a thread),
so these routes live in apps.threads under the /api/files/ prefix.
"""

from rest_framework.routers import DefaultRouter

from apps.threads.files_views import UserFileViewSet

router = DefaultRouter()
router.register(r"", UserFileViewSet, basename="userfile")
urlpatterns = router.urls
