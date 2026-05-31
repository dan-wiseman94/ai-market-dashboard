import { useSchwabStatus } from "@/hooks/useSchwabStatus";
import { fetchSchwabAuthorizeUrl } from "@/api/schwab";
import { formatDistanceToNow } from "date-fns";
import SettingsSection from "@/components/settings/SettingsSection";
import SymbolCalendarOverridesCard from "@/components/SymbolCalendarOverridesCard";
import { useToast } from "@/hooks/useToast";

export default function ConnectionsSettings() {
  const { data, isLoading } = useSchwabStatus();
  const { push } = useToast();
  const connected = data?.connected ?? false;

  const onConnect = async () => {
    try {
      const { url } = await fetchSchwabAuthorizeUrl();
      window.location.href = url;
    } catch (e) {
      // e.g. schwab_not_configured — surface the backend message instead of silently
      // failing or bouncing to Schwab's opaque 401 invalid_client page.
      push({ kind: "error", text: (e as Error).message });
    }
  };

  return (
    <SettingsSection title="Connections" description="Market-data and brokerage links.">
      <div className="ledger-surface p-5" data-testid="schwab-card">
        <div className="flex items-center gap-3">
          <h3 className="font-display text-[1.05rem] text-ink-50">Charles Schwab</h3>
          {!isLoading && (
            <span className="ledger-pill" data-tone={connected ? "gain" : "loss"}>
              {connected ? "Connected" : "Not connected"}
            </span>
          )}
        </div>
        <p className="mt-2 text-[13px] text-ink-300">
          Powers live quotes, OHLC history, option chains, and positions.
        </p>
        {isLoading ? (
          <p className="mt-3 text-ink-400 text-sm">Checking…</p>
        ) : (
          <>
            {connected && data?.expires_at && (
              <p className="mt-2 font-mono text-[11px] text-ink-400">
                token refreshes in {formatDistanceToNow(new Date(data.expires_at))}
              </p>
            )}
            <button type="button" onClick={onConnect} className="ledger-cta mt-4">
              {connected ? "Reconnect" : "Connect Schwab"}
            </button>
          </>
        )}
      </div>
      <div className="mt-4">
        <SymbolCalendarOverridesCard />
      </div>
    </SettingsSection>
  );
}
