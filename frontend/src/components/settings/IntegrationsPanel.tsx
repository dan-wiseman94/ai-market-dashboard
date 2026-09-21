import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { ApiError, apiPost } from "@/api/client";
import { SkeletonRows } from "@/components/Skeleton";

/* ── The MCP-out server ────────────────────────────────────────────────────────
 * `POST /api/mcp/` is a minimal JSON-RPC 2.0 MCP server exposing the second brain
 * (house view / theses / predictions / recall) read-only to EXTERNAL agents. It is
 * the one endpoint in the app built to be reached from outside, so it carries an
 * opt-in shared-token gate (`MCP_AUTH_TOKEN`).
 *
 * There is no status endpoint for that token, and there must not be one that
 * echoes it back. Instead this panel probes the endpoint itself with an
 * unauthenticated `tools/list`: a 401 proves a token is required, a 200 proves the
 * server is open. That yields the boolean the operator needs — and only the
 * boolean; the token value never reaches the browser.
 * ────────────────────────────────────────────────────────────────────────────── */

const MCP_PATH = "/api/mcp/";

const MCP_TOOLS: ReadonlyArray<{ name: string; description: string }> = [
  { name: "house_view", description: "The current house view for a ticker — stance, conviction, bull/bear case." },
  { name: "theses", description: "Tracked trade theses, filterable by ticker and status." },
  { name: "predictions", description: "AI directional calls from the ledger, filterable by ticker and status." },
  { name: "recall_search", description: "Semantic + keyword search across snapshots, theses and observations." },
];

const TOOL_DESCRIPTIONS: Record<string, string> = Object.fromEntries(
  MCP_TOOLS.map((t) => [t.name, t.description]),
);

interface McpProbe {
  /** True when the server answered 401 without a bearer token. */
  tokenRequired: boolean;
  /** Tool names as the live server reports them (empty when the probe was gated). */
  tools: string[];
}

interface ToolsListResult {
  result?: { tools?: Array<{ name?: string }> };
}

async function probeMcp(): Promise<McpProbe> {
  try {
    const body = await apiPost<ToolsListResult>(MCP_PATH, {
      jsonrpc: "2.0",
      id: 1,
      method: "tools/list",
    });
    const tools = (body.result?.tools ?? [])
      .map((t) => t.name)
      .filter((n): n is string => typeof n === "string");
    return { tokenRequired: false, tools };
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) {
      return { tokenRequired: true, tools: [] };
    }
    throw e;
  }
}

function endpointUrl(): string {
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  return `${origin}${MCP_PATH}`;
}

function clientConfig(url: string, tokenRequired: boolean): string {
  const server: Record<string, unknown> = { type: "http", url };
  if (tokenRequired) {
    // A placeholder, never the real token — the browser is never told the value.
    server.headers = { Authorization: "Bearer <your MCP_AUTH_TOKEN>" };
  }
  return JSON.stringify({ mcpServers: { "ledger-second-brain": server } }, null, 2);
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  const onCopy = async () => {
    // Clipboard access can be absent (non-secure context) or denied. The config is
    // rendered in full below either way, so the user can always select and copy it —
    // but never claim "Copied" when nothing was written.
    const clip = navigator.clipboard;
    if (!clip) return;
    try {
      await clip.writeText(text);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };
  return (
    <button type="button" onClick={() => void onCopy()} className="ledger-cta px-2 py-1 text-[11px]">
      {copied ? "Copied" : label}
    </button>
  );
}

function TokenPill({ tokenRequired }: { tokenRequired: boolean }) {
  return (
    <span className="ledger-pill" data-tone={tokenRequired ? "gain" : "loss"}>
      {tokenRequired ? "Token configured" : "No token configured"}
    </span>
  );
}

export default function IntegrationsPanel() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["mcp/probe"],
    queryFn: probeMcp,
    retry: false,
    staleTime: 60_000,
  });

  const url = endpointUrl();
  const toolNames = data && data.tools.length > 0 ? data.tools : MCP_TOOLS.map((t) => t.name);

  return (
    <div className="ledger-surface p-5" data-testid="mcp-card">
      <div className="flex items-center gap-3">
        <h3 className="font-display text-[1.05rem] text-ink-50">MCP server</h3>
        {data && <TokenPill tokenRequired={data.tokenRequired} />}
      </div>
      <p className="mt-2 text-[13px] text-ink-300">
        Exposes this app&rsquo;s second brain read-only to external agents (Claude Desktop, another
        CLI) — set a shared token before exposing it beyond localhost.
      </p>

      {isLoading ? (
        <div className="mt-4">
          <SkeletonRows rows={2} />
        </div>
      ) : isError || !data ? (
        <p role="alert" className="mt-3 text-[13px] text-loss-300">
          Could not reach the MCP endpoint, so its token state is unknown.
        </p>
      ) : (
        <p className="mt-3 text-[12px] text-ink-400">
          {data.tokenRequired
            ? "A shared token is set. Clients must send it as an Authorization: Bearer header; the value is never shown here."
            : "No shared token is set — anything that can reach this host can read the second brain. Set MCP_AUTH_TOKEN before exposing the endpoint."}
        </p>
      )}

      <dl className="mt-4 grid gap-1">
        <dt className="text-[12px] text-ink-300">Endpoint</dt>
        <dd className="font-mono text-[12px] text-ink-100">
          POST <span data-testid="mcp-endpoint">{url}</span>
        </dd>
      </dl>

      <h4 className="mt-4 text-[12px] uppercase tracking-wide text-ink-400">Tools (read-only)</h4>
      <ul className="mt-1 grid gap-1">
        {toolNames.map((name) => (
          <li key={name} className="text-[12px] text-ink-300">
            <span className="font-mono text-ink-100">{name}</span>
            {TOOL_DESCRIPTIONS[name] ? ` — ${TOOL_DESCRIPTIONS[name]}` : ""}
          </li>
        ))}
      </ul>

      <div className="mt-4 flex items-center justify-between gap-3">
        <h4 className="text-[12px] uppercase tracking-wide text-ink-400" id="mcp-config-label">
          Client config
        </h4>
        <CopyButton text={clientConfig(url, data?.tokenRequired ?? false)} label="Copy config" />
      </div>
      <pre
        aria-labelledby="mcp-config-label"
        className="mt-1 overflow-x-auto rounded-ledger border border-rule p-3 font-mono text-[11px] text-ink-200"
      >
        {clientConfig(url, data?.tokenRequired ?? false)}
      </pre>
    </div>
  );
}
