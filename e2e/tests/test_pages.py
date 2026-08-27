"""POM shape tests — every page class exposes the agreed surface.

These do not drive the browser; they only assert the class API exists. The
real journeys live in ``e2e/ui/``.
"""

from __future__ import annotations

import inspect


def _names(cls: type) -> set[str]:
    members = inspect.getmembers(
        cls, predicate=lambda m: inspect.isfunction(m) or isinstance(m, property)
    )
    return {name for name, _ in members}


def test_base_page_has_expected_methods() -> None:
    from e2e.pages.base import BasePage

    required = {
        "goto",
        "wait_ready",
        "expect_toast",
        "expect_error_boundary_absent",
        "open_command_palette",
        "run_shortcut",
        "current_crumb_trail",
        "notification_bell",
        "connection_dot",
        "breadcrumb_trail",
    }
    actual = _names(BasePage)
    missing = required - actual
    assert not missing, f"BasePage missing: {missing}"


def test_dashboard_page_surface() -> None:
    from e2e.pages.dashboard import DashboardPage

    for m in (
        "go",
        "hero_heading",
        "market_context_section",
        "book_section",
        "cost_chip",
        "open_notification_drawer",
    ):
        assert m in _names(DashboardPage), f"DashboardPage missing {m}"


def test_snapshot_page_surface() -> None:
    from e2e.pages.snapshot import SnapshotPage

    for m in (
        "go",
        "profile_select",
        "objective_input",
        "capture_btn",
        "send_ai_btn",
        "capture",
        "wait_for_complete",
        "send_to_ai",
        "open_compare",
    ):
        assert m in _names(SnapshotPage), f"SnapshotPage missing {m}"


def test_threads_pages() -> None:
    from e2e.pages.thread_detail import ThreadDetailPage
    from e2e.pages.threads import ThreadsListPage

    for m in ("go", "open", "filter", "thread_row", "filter_input", "pagination_next"):
        assert m in _names(ThreadsListPage)
    for m in (
        "go",
        "compose",
        "stop_btn",
        "branch_tab",
        "cost_tile",
        "send",
        "stop",
        "attach_file",
        "wait_for_done",
    ):
        assert m in _names(ThreadDetailPage)


def test_observer_pages() -> None:
    from e2e.pages.observer import ObserverTimelinePage
    from e2e.pages.schedules import SchedulesPage

    for m in ("go", "fire_rows", "scroll_to_day"):
        assert m in _names(ObserverTimelinePage)
    for m in (
        "go",
        "create_btn",
        "interval_input",
        "mode_select",
        "structured_toggle",
        "run_now_btn",
        "enabled_checkbox",
        "create",
        "run_now",
        "set_enabled",
    ):
        assert m in _names(SchedulesPage)


def test_triggers_pages() -> None:
    from e2e.pages.trigger_editor import TriggerEditorPage
    from e2e.pages.triggers import TriggersListPage

    for m in ("go", "new_btn", "row", "firings_tab", "open"):
        assert m in _names(TriggersListPage)
    for m in (
        "go_new",
        "go",
        "name",
        "ticker",
        "metric",
        "op",
        "value",
        "dsl_json",
        "backtest_btn",
        "fire_now_btn",
        "fill_simple",
        "fill_dsl",
        "backtest",
        "save",
    ):
        assert m in _names(TriggerEditorPage)


def test_analytics_page_surface() -> None:
    from e2e.pages.analytics import AnalyticsPage

    for m in (
        "go",
        "card",
        "card_leaderboard",
        "card_cpi",
        "card_heatmap",
        "card_timeline",
        "card_unusual",
        "set_ticker",
        "set_forward_hours",
    ):
        assert m in _names(AnalyticsPage)


def test_watchlist_pages() -> None:
    from e2e.pages.market_ticker import MarketTickerPage
    from e2e.pages.watchlist_detail import WatchlistDetailPage
    from e2e.pages.watchlists import WatchlistsPage

    for m in ("go", "list_item", "create_btn", "create", "open"):
        assert m in _names(WatchlistsPage)
    for m in ("go", "ticker_row", "add_input", "remove_btn", "add", "remove"):
        assert m in _names(WatchlistDetailPage)
    for m in ("go", "ohlc_chart", "news_list", "positions_tile"):
        assert m in _names(MarketTickerPage)


def test_profiles_costs_snapshotcost_pages() -> None:
    from e2e.pages.costs import CostsPage
    from e2e.pages.profiles import ProfilesPage
    from e2e.pages.snapshot_cost import SnapshotCostPage

    for m in ("go", "row", "name_input", "style_input", "create_btn", "create"):
        assert m in _names(ProfilesPage)
    for m in (
        "go",
        "today_tile",
        "provider_table",
        "csv_btn",
        "caps_editor",
        "export_csv",
        "set_caps",
    ):
        assert m in _names(CostsPage)
    for m in ("go", "section_row", "cost_total"):
        assert m in _names(SnapshotCostPage)


def test_backups_export_settings_oauth() -> None:
    from e2e.pages.backups import BackupsPage
    from e2e.pages.export import ExportPage
    from e2e.pages.schwab_oauth import SchwabOAuthPage
    from e2e.pages.settings import SettingsPage

    for m in (
        "go",
        "backup_now_btn",
        "row",
        "restore_btn",
        "download_btn",
        "backup_now",
        "restore",
        "download",
    ):
        assert m in _names(BackupsPage)
    for m in ("go", "start_btn", "row", "download_btn", "start", "download"):
        assert m in _names(ExportPage)
    for m in ("go", "api_key_input", "save_btn", "save_api_key"):
        assert m in _names(SettingsPage)
    for m in ("go", "connect_btn", "status_pill", "connect"):
        assert m in _names(SchwabOAuthPage)
