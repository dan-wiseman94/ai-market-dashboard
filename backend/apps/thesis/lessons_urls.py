"""URLConf for distilled lessons (/api/lessons/). Lesson moved into apps.thesis
(the learning leg of the thesis loop) per the 27→15 consolidation; path unchanged.
"""

from rest_framework.routers import DefaultRouter

from apps.thesis.lessons_views import LessonViewSet

router = DefaultRouter()
router.register("", LessonViewSet, basename="lesson")
urlpatterns = router.urls
