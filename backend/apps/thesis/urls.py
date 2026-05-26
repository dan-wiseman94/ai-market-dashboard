from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("theses", views.ThesisViewSet, basename="thesis")
router.register("journal", views.JournalEntryViewSet, basename="journal")

urlpatterns = router.urls
