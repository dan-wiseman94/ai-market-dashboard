import { createBrowserRouter } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Settings from "./pages/Settings";
import WatchlistsList from "./pages/WatchlistsList";
import WatchlistDetail from "./pages/WatchlistDetail";
import MarketTicker from "./pages/MarketTicker";
import ProfilesPage from "./pages/ProfilesPage";
import SnapshotComposerPage from "./pages/SnapshotComposerPage";
import ThreadDetailPage from "./pages/ThreadDetailPage";
import ThreadsPage from "./pages/ThreadsPage";
import CostsPage from "./pages/CostsPage";

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
]);
