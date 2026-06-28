"""URLConf for the Anthropic Files API proxy (GET/POST/DELETE /api/files/...).

UserFile is a thread concern (file attachments become document blocks on a thread),
so the former model-less-after-move apps.files was folded into apps.threads per the
27→15 consolidation plan. The /api/files/ paths are unchanged (no OpenAPI drift).
"""

from rest_framework.routers import DefaultRouter

from apps.threads.files_views import UserFileViewSet

router = DefaultRouter()
router.register(r"", UserFileViewSet, basename="userfile")
urlpatterns = router.urls
