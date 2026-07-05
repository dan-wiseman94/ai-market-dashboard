"""URLConf for distilled lessons (/api/lessons/), served by apps.thesis
(Lesson is the learning leg of the thesis loop).
"""

from rest_framework.routers import DefaultRouter

from apps.thesis.lessons_views import LessonViewSet

router = DefaultRouter()
router.register("", LessonViewSet, basename="lesson")
urlpatterns = router.urls
