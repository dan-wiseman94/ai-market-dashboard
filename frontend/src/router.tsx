import { createBrowserRouter } from "react-router-dom";
import AppLayout from "./components/layout/AppLayout";
import Dashboard from "./pages/Dashboard";
import Settings from "./pages/Settings";
import WatchlistsList from "./pages/WatchlistsList";
import WatchlistDetail from "./pages/WatchlistDetail";
import MarketTicker from "./pages/MarketTickerPage";
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

export const router = createBrowserRouter([
  // Render route bypasses AppLayout — it's for headless-chromium PNG captures.
  { path: "/render/chart", element: <RenderChart /> },
  {
    path: "/",
    element: <AppLayout />,
    handle: { crumb: "Home" },
    children: [
      { index: true, element: <Dashboard />, handle: { crumb: "Dashboard" } },
      { path: "settings", element: <Settings />, handle: { crumb: "Settings" } },
      { path: "watchlists", element: <WatchlistsList />, handle: { crumb: "Watchlists" } },
      { path: "watchlists/:id", element: <WatchlistDetail />,
        handle: { crumb: ({ params }: { params: { id?: string } }) => `Watchlist ${params.id}` } },
      { path: "market/:ticker", element: <MarketTicker />,
        handle: { crumb: ({ params }: { params: { ticker?: string } }) => params.ticker?.toUpperCase() ?? "Market" } },
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
    ],
  },
]);
