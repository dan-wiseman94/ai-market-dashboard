import { useSchwabStatus } from "@/hooks/useSchwabStatus";
import { fetchSchwabAuthorizeUrl } from "@/api/schwab";
import { formatDistanceToNow } from "date-fns";

export default function SchwabConnectionCard() {
  const { data, isLoading } = useSchwabStatus();
  if (isLoading) return <div className="p-4 rounded border border-slate-800">Checking Schwab…</div>;

  const connected = data?.connected ?? false;

  const onConnect = async () => {
    const { url } = await fetchSchwabAuthorizeUrl();
    window.location.href = url;
  };

  return (
    <div className="p-4 rounded border border-slate-800 space-y-2">
      <h2 className="text-lg font-medium">Charles Schwab</h2>
      {connected ? (
        <p className="text-emerald-400">
          Connected
          {data?.expires_at && <> · token refreshes in {formatDistanceToNow(new Date(data.expires_at))}</>}
        </p>
      ) : (
        <p className="text-rose-400">Not connected</p>
      )}
      <button
        onClick={onConnect}
        className="px-3 py-1.5 rounded bg-slate-700 hover:bg-slate-600 text-sm"
      >
        {connected ? "Reconnect" : "Connect Schwab"}
      </button>
    </div>
  );
}
