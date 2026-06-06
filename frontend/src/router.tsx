import { createBrowserRouter } from "react-router-dom";
import AppLayout from "./components/layout/AppLayout";
import Dashboard from "./pages/Dashboard";
import SettingsLayout from "./pages/settings/SettingsLayout";
import ProvidersSettings from "./pages/settings/ProvidersSettings";
import ConnectionsSettings from "./pages/settings/ConnectionsSettings";
import SystemSettings from "./pages/settings/SystemSettings";
import WatchlistsList from "./pages/WatchlistsList";
import WatchlistDetail from "./pages/WatchlistDetail";
import MarketTicker from "./pages/MarketTickerPage";
import MarketDataPage from "./pages/MarketDataPage";
import ProfilesPage from "./pages/ProfilesPage";
import SnapshotComposerPage from "./pages/SnapshotComposerPage";
import ThreadDetailPage from "./pages/ThreadDetailPage";
import ThreadsPage from "./pages/ThreadsPage";
import CostsPage from "./pages/CostsPage";
import RenderChart from "./pages/RenderChart";
import SchedulesPage from "./pages/SchedulesPage";
import ObserverTimelinePage from "./pages/ObserverTimelinePage";
import TriggersListPage from "./pages/TriggersListPage";
import TriggerEditorPage from "./pages/TriggerEditorPage";
import SnapshotCostPage from "./pages/SnapshotCostPage";
import BackupsPage from "./pages/BackupsPage";
import ExportPage from "./pages/ExportPage";
import AnalyticsPage from "./pages/AnalyticsPage";
import ScorecardPage from "./pages/ScorecardPage";
import MirrorPage from "./pages/MirrorPage";
import CoveragePage from "./pages/CoveragePage";
import ThesesPage from "./pages/ThesesPage";
import NewThesisPage from "./pages/NewThesisPage";
import ThesisDetailPage from "./pages/ThesisDetailPage";
import EventsPage from "./pages/EventsPage";
import BriefingPage from "./pages/BriefingPage";
import SnapshotsPage from "./pages/SnapshotsPage";
import RecallPage from "./pages/RecallPage";
import ErrorsPage from "./pages/ErrorsPage";
import RegimePage from "./pages/RegimePage";
import BookPage from "./pages/BookPage";
import WarRoomPage from "@/pages/WarRoomPage";
import WarRoomDetailPage from "@/pages/WarRoomDetailPage";
import DeskPage from "@/pages/DeskPage";
import PortfolioPage from "./pages/PortfolioPage";

export const router = createBrowserRouter([
  // Render route bypasses AppLayout — it's for headless-chromium PNG captures.
  { path: "/render/chart", element: <RenderChart /> },
  {
    path: "/",
    element: <AppLayout />,
    handle: { crumb: "Home" },
    children: [
      { index: true, element: <Dashboard />, handle: { crumb: "Dashboard" } },
      {
        path: "settings",
        element: <SettingsLayout />,
        handle: { crumb: "Settings" },
        children: [
          { index: true, element: <ProvidersSettings />, handle: { crumb: "AI Providers" } },
          { path: "connections", element: <ConnectionsSettings />, handle: { crumb: "Connections" } },
          { path: "system", element: <SystemSettings />, handle: { crumb: "System" } },
          { path: "backups", element: <BackupsPage />, handle: { crumb: "Backups" } },
          { path: "export", element: <ExportPage />, handle: { crumb: "Export" } },
        ],
      },
      { path: "watchlists", element: <WatchlistsList />, handle: { crumb: "Watchlists" } },
      { path: "watchlists/:id", element: <WatchlistDetail />,
        handle: { crumb: ({ params }: { params: { id?: string } }) => `Watchlist ${params.id}` } },
      { path: "market/:ticker", element: <MarketTicker />,
        handle: { crumb: ({ params }: { params: { ticker?: string } }) => params.ticker?.toUpperCase() ?? "Market" } },
      { path: "market-data", element: <MarketDataPage />, handle: { crumb: "Market data" } },
      { path: "profiles", element: <ProfilesPage />, handle: { crumb: "Profiles" } },
      { path: "snapshot", element: <SnapshotComposerPage />, handle: { crumb: "Snapshot" } },
      { path: "threads", element: <ThreadsPage />, handle: { crumb: "Threads" } },
      { path: "threads/:id", element: <ThreadDetailPage />,
        handle: { crumb: ({ params }: { params: { id?: string } }) => `Thread ${params.id}` } },
      { path: "threads/observer/:profileId", element: <ObserverTimelinePage />,
        handle: { crumb: "Observer timeline" } },
      { path: "costs", element: <CostsPage />, handle: { crumb: "Costs" } },
      { path: "costs/snapshot/:id", element: <SnapshotCostPage />,
        handle: { crumb: ({ params }: { params: { id?: string } }) => `Snapshot ${params.id}` } },
      { path: "schedules", element: <SchedulesPage />, handle: { crumb: "Schedules" } },
      { path: "triggers", element: <TriggersListPage />, handle: { crumb: "Triggers" } },
      { path: "triggers/new", element: <TriggerEditorPage />, handle: { crumb: "New trigger" } },
      { path: "triggers/:id", element: <TriggerEditorPage />,
        handle: { crumb: ({ params }: { params: { id?: string } }) => `Trigger ${params.id}` } },
      { path: "events", element: <EventsPage />, handle: { crumb: "Events" } },
      { path: "briefing", element: <BriefingPage />, handle: { crumb: "Briefing" } },
      { path: "snapshots", element: <SnapshotsPage />, handle: { crumb: "Snapshots" } },
      { path: "analytics", element: <AnalyticsPage />, handle: { crumb: "Analytics" } },
      { path: "scorecard", element: <ScorecardPage />, handle: { crumb: "Scorecard" } },
      { path: "mirror", element: <MirrorPage />, handle: { crumb: "The Mirror" } },
      { path: "regime", element: <RegimePage />, handle: { crumb: "Regime" } },
      { path: "book", element: <BookPage />, handle: { crumb: "Book" } },
      { path: "warroom", element: <WarRoomPage />, handle: { crumb: "War Room" } },
      { path: "warroom/:id", element: <WarRoomDetailPage />, handle: { crumb: "Debate" } },
      { path: "desk", element: <DeskPage />, handle: { crumb: "Desk" } },
      { path: "portfolio", element: <PortfolioPage />, handle: { crumb: "Portfolio" } },
      { path: "coverage/:ticker", element: <CoveragePage />,
        handle: { crumb: ({ params }: { params: { ticker?: string } }) => params.ticker?.toUpperCase() ?? "Coverage" } },
      { path: "theses", element: <ThesesPage />, handle: { crumb: "Theses" } },
      { path: "theses/new", element: <NewThesisPage />, handle: { crumb: "New thesis" } },
      { path: "recall", element: <RecallPage />, handle: { crumb: "Recall" } },
      { path: "errors", element: <ErrorsPage />, handle: { crumb: "Errors" } },
      {
        path: "theses/:id",
        element: <ThesisDetailPage />,
        handle: {
          crumb: ({ params }: { params: { id?: string } }) =>
            `Thesis ${params.id}`,
        },
      },
    ],
  },
]);
