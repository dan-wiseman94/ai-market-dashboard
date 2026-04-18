import { createBrowserRouter } from "react-router-dom";
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

export const router = createBrowserRouter([
  { path: "/", element: <Dashboard /> },
  { path: "/settings", element: <Settings /> },
  { path: "/watchlists", element: <WatchlistsList /> },
  { path: "/watchlists/:id", element: <WatchlistDetail /> },
  { path: "/market/:ticker", element: <MarketTicker /> },
  { path: "/profiles", element: <ProfilesPage /> },
  { path: "/snapshot", element: <SnapshotComposerPage /> },
  { path: "/threads", element: <ThreadsPage /> },
  { path: "/threads/:id", element: <ThreadDetailPage /> },
  { path: "/costs", element: <CostsPage /> },
  { path: "/render/chart", element: <RenderChart /> },
  { path: "/schedules", element: <SchedulesPage /> },
  { path: "/threads/observer/:profileId", element: <ObserverTimelinePage /> },
  { path: "/triggers", element: <TriggersListPage /> },
  { path: "/triggers/new", element: <TriggerEditorPage /> },
  { path: "/triggers/:id", element: <TriggerEditorPage /> },
]);
