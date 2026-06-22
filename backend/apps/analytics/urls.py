from django.urls import path

from apps.analytics.views import (
    AICalibrationDrilldownView,
    AICalibrationView,
    CalibrationDriftView,
    CalibrationDrilldownView,
    CalibrationView,
    ContradictionsView,
    CostPerInsightView,
    LeaderboardView,
    ObserverTimelineView,
    TrackRecordView,
    TraderCalibrationView,
    TriggerHeatmapView,
    UnusualOptionsView,
)

urlpatterns = [
    path("calibration/", CalibrationView.as_view(), name="analytics-calibration"),
    path("calibration-drift/", CalibrationDriftView.as_view(), name="analytics-calibration-drift"),
    path("contradictions/", ContradictionsView.as_view(), name="analytics-contradictions"),
    path(
        "calibration/drilldown/",
        CalibrationDrilldownView.as_view(),
        name="analytics-calibration-drilldown",
    ),
    path("leaderboard/", LeaderboardView.as_view(), name="analytics-leaderboard"),
    path("cost-per-insight/", CostPerInsightView.as_view(), name="analytics-cpi"),
    path("trigger-heatmap/", TriggerHeatmapView.as_view(), name="analytics-heatmap"),
    path("observer-timeline/", ObserverTimelineView.as_view(), name="analytics-timeline"),
    path(
        "unusual-options/",
        UnusualOptionsView.as_view(),
        name="analytics-unusual-options",
    ),
    path("track-record/", TrackRecordView.as_view(), name="analytics-track-record"),
    path("ai-calibration/", AICalibrationView.as_view(), name="analytics-ai-calibration"),
    path(
        "ai-calibration/drilldown/",
        AICalibrationDrilldownView.as_view(),
        name="analytics-ai-calibration-drilldown",
    ),
    path(
        "trader-calibration/",
        TraderCalibrationView.as_view(),
        name="analytics-trader-calibration",
    ),
]
