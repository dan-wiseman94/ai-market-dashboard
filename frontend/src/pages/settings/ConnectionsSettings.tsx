import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useSchwabStatus, useSchwabAppConfig } from "@/hooks/useSchwabStatus";
import { fetchSchwabAuthorizeUrl, updateSchwabAppConfig } from "@/api/schwab";
import { formatDistanceToNow } from "date-fns";
import SettingsSection from "@/components/settings/SettingsSection";
import DataSourcesPanel from "@/components/settings/DataSourcesPanel";
import SymbolCalendarOverridesCard from "@/components/SymbolCalendarOverridesCard";
import { useToast } from "@/hooks/useToast";

export default function ConnectionsSettings() {
  const { data, isLoading } = useSchwabStatus();
  const { data: appCfg } = useSchwabAppConfig();
  const { push } = useToast();
  const qc = useQueryClient();
  const connected = data?.connected ?? false;
  const configured = appCfg?.configured ?? false;

  // Derive the client_id input from the server value until the user edits it (avoids the
  // react-hooks/set-state-in-effect lint error from syncing props into state in an effect).
  const [clientIdDraft, setClientIdDraft] = useState<string | null>(null);
  const [secret, setSecret] = useState("");
  const [saving, setSaving] = useState(false);
  const clientId = clientIdDraft ?? appCfg?.client_id ?? "";

  const onSaveCreds = async () => {
    setSaving(true);
    try {
      await updateSchwabAppConfig({
        client_id: clientId.trim(),
        client_secret_write: secret || undefined,
      });
      setSecret("");
      setClientIdDraft(null); // re-sync the input to the freshly-saved server value
      await qc.invalidateQueries({ queryKey: ["schwab"] });
      push({ kind: "success", text: "Schwab credentials saved." });
    } catch (e) {
      push({ kind: "error", text: (e as Error).message });
    } finally {
      setSaving(false);
    }
  };

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

        <div className="mt-4 grid gap-3">
          <label className="grid gap-1">
            <span className="text-[12px] text-ink-300">App Key (Client ID)</span>
            <input
              type="text"
              aria-label="Schwab App Key"
              value={clientId}
              onChange={(e) => setClientIdDraft(e.target.value)}
              placeholder="your Schwab app key"
              className="ledger-input w-full py-2 font-mono text-[12px]"
            />
          </label>
          <label className="grid gap-1">
            <span className="text-[12px] text-ink-300">Secret</span>
            <input
              type="password"
              aria-label="Schwab Secret"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              placeholder={appCfg?.client_secret_present ? "•••••••• (unchanged)" : "your Schwab app secret"}
              className="ledger-input w-full py-2 font-mono text-[12px]"
            />
          </label>
          <div>
            <button
              type="button"
              onClick={onSaveCreds}
              disabled={saving}
              className="ledger-cta"
            >
              {saving ? "Saving…" : "Save credentials"}
            </button>
          </div>
        </div>

        {isLoading ? (
          <p className="mt-3 text-ink-400 text-sm">Checking…</p>
        ) : (
          <>
            {connected && data?.expires_at && (
              <p className="mt-2 font-mono text-[11px] text-ink-400">
                token refreshes in {formatDistanceToNow(new Date(data.expires_at))}
              </p>
            )}
            {!configured && (
              <p className="mt-3 text-[12px] text-ink-400">
                Add your Schwab API credentials above before connecting.
              </p>
            )}
            <button
              type="button"
              onClick={onConnect}
              disabled={!configured}
              className="ledger-cta mt-4"
            >
              {connected ? "Reconnect" : "Connect Schwab"}
            </button>
          </>
        )}
      </div>
      <div className="mt-6">
        <DataSourcesPanel />
      </div>
      <div className="mt-4">
        <SymbolCalendarOverridesCard />
      </div>
    </SettingsSection>
  );
}
