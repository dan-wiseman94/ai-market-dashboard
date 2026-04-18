import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { usd } from "@/utils/format";

type Props = {
  role: "user" | "assistant" | "system";
  text: string;
  status?: "done" | "streaming" | "failed";
  error?: string;
  cost?: string;
  model?: string;
  provider?: string;
  /** When true, render without the outer ledger-surface (caller provides one). */
  bare?: boolean;
};

function Message({ role, text, status, error, cost, model, provider, bare = false }: Props) {
  const isUser = role === "user";
  const isStreaming = status === "streaming";

  if (isUser) {
    return (
      <article className="relative group ledger-reveal pl-5">
        <div
          aria-hidden
          className="absolute left-0 top-1.5 bottom-1.5 w-[2px]"
          style={{
            background:
              "linear-gradient(180deg, transparent 0%, color-mix(in srgb, var(--copper-500) 60%, transparent) 30%, color-mix(in srgb, var(--copper-500) 60%, transparent) 70%, transparent 100%)",
          }}
        />
        <div className="flex items-center gap-2 mb-1">
          <span className="ledger-eyebrow" style={{ color: "var(--copper-300)" }}>You</span>
        </div>
        <div
          className="text-ink-100 text-[15px] leading-[1.7] font-display whitespace-pre-wrap"
          style={{ fontVariationSettings: '"opsz" 18, "SOFT" 40' }}
        >
          {text || <span className="italic text-ink-400">(empty)</span>}
        </div>
      </article>
    );
  }

  const label = provider
    ? provider.charAt(0).toUpperCase() + provider.slice(1)
    : "Assistant";

  const innerClass = bare ? "px-0 py-0" : "ledger-surface px-6 py-5";

  return (
    <article className="relative group ledger-reveal">
      <div className={innerClass}>
        <header className="flex items-center gap-3 mb-4 pb-3 border-b border-rule-soft">
          <span className="relative inline-flex items-center justify-center h-6 w-6 rounded-full bg-copper-500/15 border border-copper-500/40">
            <span className="font-mono text-[10px] text-copper-300">AI</span>
            {isStreaming && (
              <span aria-hidden className="absolute inset-0 rounded-full ledger-pulse text-copper-400" />
            )}
          </span>
          <div className="flex flex-col min-w-0">
            <span className="font-mono text-[11px] text-ink-200 tracking-wide truncate">
              {label}
              {model && <span className="text-ink-500"> · {model}</span>}
            </span>
            {isStreaming && (
              <span className="font-mono text-[9px] uppercase tracking-loose2 text-copper-400">
                Transmitting…
              </span>
            )}
          </div>
          <div className="flex-1" />
          {cost && (
            <span className="ledger-pill" data-tone="copper">
              <span className="text-ink-500">cost</span>
              <span className="tabular-nums">{usd(cost)}</span>
            </span>
          )}
        </header>

        {status === "failed" ? (
          <div className="text-loss font-mono text-[13px]">
            <span className="ledger-pill mr-2" data-tone="loss">failed</span>
            {error || "unknown error"}
          </div>
        ) : (
          <div className="ledger-prose">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {text || (isStreaming ? "…" : "")}
            </ReactMarkdown>
            {isStreaming && text && (
              <span
                aria-hidden
                className="inline-block w-2 h-4 ml-0.5 align-text-bottom bg-copper-400 ledger-pulse"
                style={{ color: "var(--copper-400)" }}
              />
            )}
          </div>
        )}
      </div>
    </article>
  );
}

export default memo(Message);
