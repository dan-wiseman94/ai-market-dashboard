import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Props = {
  role: "user" | "assistant" | "system";
  text: string;
  status?: "done" | "streaming" | "failed";
  error?: string;
  cost?: string;
  model?: string;
};

function Message({ role, text, status, error, cost, model }: Props) {
  const isAssistant = role === "assistant";
  return (
    <div className={`p-4 rounded border ${
      isAssistant ? "border-emerald-900/50 bg-emerald-950/20" : "border-slate-800"
    }`}>
      <div className="flex justify-between text-xs text-slate-500 mb-2">
        <span>{role}{model ? ` · ${model}` : ""}</span>
        {cost && <span>${Number(cost).toFixed(4)}</span>}
      </div>
      {status === "failed" ? (
        <p className="text-rose-400">Error: {error || "unknown"}</p>
      ) : (
        <div className="prose prose-invert prose-sm max-w-none">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{text || (status === "streaming" ? "…" : "")}</ReactMarkdown>
        </div>
      )}
    </div>
  );
}

export default memo(Message);
