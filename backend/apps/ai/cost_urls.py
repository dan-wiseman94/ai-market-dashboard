"""URLConf for cost reporting (GET /api/costs/...).

Billing is one domain with apps.ai.cost; the model-less ``costs`` app was folded
into apps.ai per the 27→15 consolidation plan. The /api/costs/ paths are unchanged
(no OpenAPI drift), and this include MUST stay registered BEFORE the generic /api/
includes in config/urls.py (the documented include-ordering landmine).
"""

from django.urls import path

from apps.ai import cost_views as views

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
