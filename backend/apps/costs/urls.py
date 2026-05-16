from django.urls import path

from . import views

urlpatterns = [
    path("today/", views.costs_today, name="costs-today"),
    path("summary", views.costs_summary, name="costs-summary"),
    path("caps", views.costs_caps, name="costs-caps"),
    path(
        "snapshot/<int:snapshot_id>",
        views.costs_snapshot_breakdown,
        name="costs-snapshot-breakdown",
    ),
    path("export.csv", views.costs_export_csv, name="costs-export-csv"),
]
