from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.core.urls")),
    path("api/schwab/", include("apps.secrets.urls")),
    path("api/market/", include("apps.market.urls")),
    path("api/analytics/", include("apps.analytics.urls")),
    path("api/costs/", include("apps.costs.urls")),
    path("api/observer/", include("apps.observer.urls")),
    path("api/triggers/", include("apps.triggers.urls")),
    path("api/backups/", include("apps.backups.urls")),
    path("api/export/", include("apps.export.urls")),
    path("api/files/", include("apps.files.urls")),
    path("api/briefings/", include("apps.briefing.urls")),
    path("api/recall/", include("apps.recall.urls")),
    path("api/aieval/", include("apps.aieval.urls")),
    path("api/dashboard/", include("apps.dashboard.urls")),
    path("api/portfolio/", include("apps.portfolio.urls")),
    path("api/predictions/", include("apps.predictions.urls")),
    path("api/lessons/", include("apps.lessons.urls")),
    path("api/coverage/", include("apps.coverage.urls")),
    path("api/regime/", include("apps.regime.urls")),
    path("api/", include("apps.profiles.urls")),
    path("api/", include("apps.snapshots.urls")),
    path("api/", include("apps.threads.urls")),
    path("api/", include("apps.thesis.urls")),
    # SPA fallback — must be last. Excludes api/, static/, render/, ws/, admin/.
    re_path(
        r"^(?!api/|static/|render/|ws/|admin/).*$",
        TemplateView.as_view(template_name="index.html"),
        name="spa-fallback",
    ),
]
