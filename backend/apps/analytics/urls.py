from django.urls import path

from apps.analytics.views import LeaderboardView

urlpatterns = [
    path("leaderboard/", LeaderboardView.as_view(), name="analytics-leaderboard"),
]
