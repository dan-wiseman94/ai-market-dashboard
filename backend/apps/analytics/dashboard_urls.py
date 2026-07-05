"""URLConf for the command-centre rollup (GET /api/dashboard/).

The dashboard is a read-only analytics rollup, so it lives in apps.analytics
under the /api/dashboard/ path.
"""

from django.urls import path

from apps.analytics.dashboard import DashboardView

app_name = "dashboard"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
]
