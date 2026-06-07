"""URLConf for the command-centre rollup (GET /api/dashboard/).

The dashboard is a read-only analytics rollup, so it lives in apps.analytics
(formerly its own apps.dashboard app — merged per the 27→12 consolidation plan).
The /api/dashboard/ path is unchanged, so there is no OpenAPI schema drift.
"""

from django.urls import path

from apps.analytics.dashboard import DashboardView

app_name = "dashboard"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
]
