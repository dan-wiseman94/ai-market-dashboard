from django.urls import path

from apps.analytics.views import (
    CalibrationView,
    CostPerInsightView,
    LeaderboardView,
    ObserverTimelineView,
    TriggerHeatmapView,
    UnusualOptionsView,
)

urlpatterns = [
    path("calibration/", CalibrationView.as_view(), name="analytics-calibration"),
    path("leaderboard/", LeaderboardView.as_view(), name="analytics-leaderboard"),
    path("cost-per-insight/", CostPerInsightView.as_view(), name="analytics-cpi"),
    path("trigger-heatmap/", TriggerHeatmapView.as_view(), name="analytics-heatmap"),
    path("observer-timeline/", ObserverTimelineView.as_view(), name="analytics-timeline"),
    path(
        "unusual-options/",
        UnusualOptionsView.as_view(),
        name="analytics-unusual-options",
    ),
]
