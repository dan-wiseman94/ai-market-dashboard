import { useState } from "react";
import { Link } from "react-router-dom";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonRows } from "@/components/Skeleton";
import {
  usePortfolioPositions,
  useCreatePosition,
  useClosePosition,
  useDeletePosition,
} from "@/hooks/usePortfolio";
import type { PortfolioPosition, PositionDirection, PositionStatus } from "@/api/portfolio";

type ViewStatus = "open" | "closed";

function pnlColor(pnl: number): string {
  if (pnl > 0) return "text-gain-400";
  if (pnl < 0) return "text-loss-400";
  return "text-ink-400";
}

// ---- Add Position Form ----

interface AddPositionFormProps {
  onCreated: () => void;
}

function AddPositionForm({ onCreated }: AddPositionFormProps) {
  const [ticker, setTicker] = useState("");
  const [direction, setDirection] = useState<PositionDirection>("long");
  const [quantity, setQuantity] = useState("");
  const [avgCost, setAvgCost] = useState("");
  const [thesisId, setThesisId] = useState("");
  const [note, setNote] = useState("");
  const [open, setOpen] = useState(false);

  const create = useCreatePosition();

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    create.mutate(
      {
        ticker: ticker.trim().toUpperCase(),
        direction,
        quantity,
        avg_cost: avgCost,
        note: note.trim(),
        thesis_id: thesisId ? parseInt(thesisId, 10) : null,
      },
      {
        onSuccess: () => {
          setTicker("");
          setDirection("long");
          setQuantity("");
          setAvgCost("");
          setThesisId("");
          setNote("");
          setOpen(false);
          onCreated();
        },
      },
    );
  }

  if (!open) {
    return (
      <button
        data-testid="add-position-btn"
        onClick={() => setOpen(true)}
        className="ledger-ghost px-4 py-2 text-[13px]"
      >
        + Add position
      </button>
    );
  }

  return (
    <form
      data-testid="add-position-form"
      onSubmit={handleSubmit}
      className="ledger-surface px-5 py-4 space-y-4 mb-6"
    >
      <div className="ledger-eyebrow mb-1">New position</div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <label className="flex flex-col gap-1 text-[12px] text-ink-400">
          Ticker
          <input
            data-testid="input-ticker"
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            placeholder="AAPL"
            required
            className="bg-ink-void border border-rule rounded px-3 py-1.5 text-[13px] text-ink-100 focus:outline-none focus:border-copper-500"
          />
        </label>

        <label className="flex flex-col gap-1 text-[12px] text-ink-400">
          Direction
          <select
            data-testid="input-direction"
            value={direction}
            onChange={(e) => setDirection(e.target.value as PositionDirection)}
            className="bg-ink-void border border-rule rounded px-3 py-1.5 text-[13px] text-ink-100 focus:outline-none focus:border-copper-500"
          >
            <option value="long">Long</option>
            <option value="short">Short</option>
          </select>
        </label>

        <label className="flex flex-col gap-1 text-[12px] text-ink-400">
          Quantity
          <input
            data-testid="input-quantity"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            placeholder="10"
            required
            className="bg-ink-void border border-rule rounded px-3 py-1.5 text-[13px] text-ink-100 focus:outline-none focus:border-copper-500"
          />
        </label>

        <label className="flex flex-col gap-1 text-[12px] text-ink-400">
          Avg cost
          <input
            data-testid="input-avg-cost"
            value={avgCost}
            onChange={(e) => setAvgCost(e.target.value)}
            placeholder="150.00"
            required
            className="bg-ink-void border border-rule rounded px-3 py-1.5 text-[13px] text-ink-100 focus:outline-none focus:border-copper-500"
          />
        </label>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <label className="flex flex-col gap-1 text-[12px] text-ink-400">
          Thesis ID (optional)
          <input
            data-testid="input-thesis-id"
            value={thesisId}
            onChange={(e) => setThesisId(e.target.value)}
            placeholder="42"
            type="number"
            className="bg-ink-void border border-rule rounded px-3 py-1.5 text-[13px] text-ink-100 focus:outline-none focus:border-copper-500"
          />
        </label>

        <label className="flex flex-col gap-1 text-[12px] text-ink-400">
          Note (optional)
          <input
            data-testid="input-note"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Earnings play…"
            className="bg-ink-void border border-rule rounded px-3 py-1.5 text-[13px] text-ink-100 focus:outline-none focus:border-copper-500"
          />
        </label>
      </div>

      <div className="flex gap-2">
        <button
          type="submit"
          data-testid="submit-add-position"
          disabled={create.isPending}
          className="ledger-cta px-4 py-1.5 text-[13px]"
        >
          {create.isPending ? "Saving…" : "Add position"}
        </button>
        <button
          type="button"
          className="ledger-ghost px-4 py-1.5 text-[13px]"
          onClick={() => setOpen(false)}
        >
          Cancel
        </button>
      </div>
      {create.isError && (
        <p className="text-loss-400 text-[12px]">Failed to add position.</p>
      )}
    </form>
  );
}

// ---- Close Position Form (inline per-row) ----

function ClosePositionInline({
  position,
  onDone,
}: {
  position: PortfolioPosition;
  onDone: () => void;
}) {
  const [closePrice, setClosePrice] = useState("");
  const close = useClosePosition();

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    close.mutate(
      { id: position.id, body: { close_price: closePrice } },
      { onSuccess: onDone },
    );
  }

  return (
    <form
      data-testid={`close-form-${position.id}`}
      onSubmit={handleSubmit}
      className="inline-flex items-center gap-2"
    >
      <input
        data-testid={`close-price-input-${position.id}`}
        value={closePrice}
        onChange={(e) => setClosePrice(e.target.value)}
        placeholder="Close price"
        required
        className="bg-ink-void border border-rule rounded px-2 py-1 text-[12px] text-ink-100 w-28 focus:outline-none focus:border-copper-500"
      />
      <button
        type="submit"
        data-testid={`submit-close-${position.id}`}
        disabled={close.isPending}
        className="font-mono text-[11px] text-copper-400 hover:text-copper-200 disabled:opacity-50"
      >
        {close.isPending ? "…" : "Close"}
      </button>
      <button
        type="button"
        className="font-mono text-[11px] text-ink-500 hover:text-ink-300"
        onClick={onDone}
      >
        ✕
      </button>
    </form>
  );
}

// ---- Position Row ----

function PositionRow({
  position,
  showClose = false,
}: {
  position: PortfolioPosition;
  showClose?: boolean;
}) {
  const [closing, setClosing] = useState(false);
  const del = useDeletePosition();

  const pnl = position.unrealized?.unrealized_pnl ?? null;
  const pct = position.unrealized?.unrealized_pct ?? null;
  const realized = position.realized_pnl ? Number(position.realized_pnl) : null;

  return (
    <tr
      data-testid={`position-row-${position.id}`}
      className="border-b border-rule-soft hover:bg-copper-500/[0.03] transition-colors"
    >
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[13px] text-ink-100 font-medium">
            {position.ticker}
          </span>
          <span
            className={`font-mono text-[9px] uppercase tracking-loose2 border px-1 py-0.5 rounded-ledger ${
              position.direction === "long"
                ? "text-gain-400 border-gain-400/30"
                : "text-loss-400 border-loss-400/30"
            }`}
          >
            {position.direction}
          </span>
        </div>
        {position.thesis_id && (
          <Link
            to={`/theses/${position.thesis_id}`}
            className="font-mono text-[10px] text-copper-400 hover:text-copper-200 transition-colors"
          >
            Thesis #{position.thesis_id}
          </Link>
        )}
      </td>
      <td className="px-4 py-3 font-mono text-[12px] text-ink-300 tabular-nums text-right">
        {Number(position.quantity).toLocaleString()}
      </td>
      <td className="px-4 py-3 font-mono text-[12px] text-ink-300 tabular-nums text-right">
        {Number(position.avg_cost).toFixed(2)}
      </td>
      <td className="px-4 py-3 font-mono text-[12px] tabular-nums text-right">
        {position.unrealized?.last != null
          ? position.unrealized.last.toFixed(2)
          : "—"}
      </td>
      <td className="px-4 py-3 font-mono text-[12px] tabular-nums text-right">
        {pnl != null ? (
          <>
            <span
              data-testid={`pnl-${position.id}`}
              className={pnlColor(pnl)}
            >
              {pnl >= 0 ? "+" : ""}
              {pnl.toFixed(2)}
            </span>
            {pct != null && (
              <div className={`text-[10px] ${pnlColor(pnl)}`}>
                {pct >= 0 ? "+" : ""}
                {pct.toFixed(1)}%
              </div>
            )}
          </>
        ) : realized != null ? (
          <span
            data-testid={`realized-${position.id}`}
            className={pnlColor(realized)}
          >
            {realized >= 0 ? "+" : ""}
            {realized.toFixed(2)}
          </span>
        ) : (
          <span className="text-ink-600">—</span>
        )}
      </td>
      <td className="px-4 py-3 text-right">
        {showClose && position.status === "open" && (
          <>
            {closing ? (
              <ClosePositionInline
                position={position}
                onDone={() => setClosing(false)}
              />
            ) : (
              <button
                data-testid={`open-close-btn-${position.id}`}
                onClick={() => setClosing(true)}
                className="font-mono text-[11px] text-copper-400 hover:text-copper-200 transition-colors"
              >
                Close…
              </button>
            )}
          </>
        )}
        {position.status === "open" && !closing && (
          <button
            data-testid={`delete-btn-${position.id}`}
            onClick={() => del.mutate(position.id)}
            disabled={del.isPending}
            className="font-mono text-[11px] text-ink-500 hover:text-loss-400 ml-3 disabled:opacity-50"
          >
            ✕
          </button>
        )}
      </td>
    </tr>
  );
}

// ---- Positions Table ----

function PositionsTable({
  positions,
  showClose = false,
}: {
  positions: PortfolioPosition[];
  showClose?: boolean;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left">
        <thead>
          <tr className="border-b border-rule">
            <th className="px-4 py-2 ledger-eyebrow text-left">Ticker</th>
            <th className="px-4 py-2 ledger-eyebrow text-right">Qty</th>
            <th className="px-4 py-2 ledger-eyebrow text-right">Avg Cost</th>
            <th className="px-4 py-2 ledger-eyebrow text-right">Last</th>
            <th className="px-4 py-2 ledger-eyebrow text-right">P&amp;L</th>
            <th className="px-4 py-2 ledger-eyebrow text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((p) => (
            <PositionRow key={p.id} position={p} showClose={showClose} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---- Main Page ----

export default function PortfolioPage() {
  const [viewStatus, setViewStatus] = useState<ViewStatus>("open");
  const { data: positions, isLoading } = usePortfolioPositions({ status: viewStatus as PositionStatus });
  const all = positions ?? [];

  return (
    <main className="px-8 py-8 max-w-5xl mx-auto ledger-fade-in">
      <header className="mb-6 pb-4 border-b border-rule">
        <span className="ledger-eyebrow">Portfolio</span>
        <h1
          className="ledger-display"
          style={{ fontSize: "clamp(1.5rem, 2.4vw, 2rem)" }}
        >
          The Book
        </h1>
        <p className="mt-2 text-[13px] text-ink-400">
          Manually tracked positions — no broker write path. Observational only.
        </p>
      </header>

      {/* Status toggle */}
      <div className="flex items-center gap-2 mb-6">
        <button
          data-testid="view-open-btn"
          onClick={() => setViewStatus("open")}
          className={`font-mono text-[11px] px-3 py-1.5 rounded border transition-colors ${
            viewStatus === "open"
              ? "border-copper-500 text-copper-200 bg-copper-900/20"
              : "border-rule text-ink-400 hover:border-ink-400"
          }`}
        >
          Open
        </button>
        <button
          data-testid="view-closed-btn"
          onClick={() => setViewStatus("closed")}
          className={`font-mono text-[11px] px-3 py-1.5 rounded border transition-colors ${
            viewStatus === "closed"
              ? "border-copper-500 text-copper-200 bg-copper-900/20"
              : "border-rule text-ink-400 hover:border-ink-400"
          }`}
        >
          Closed
        </button>
        {all.length > 0 && (
          <span className="font-mono text-[11px] text-ink-500 ml-2">
            {all.length} position{all.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {/* Add position form (only for open view) */}
      {viewStatus === "open" && (
        <div className="mb-6">
          <AddPositionForm onCreated={() => {}} />
        </div>
      )}

      {/* Position list */}
      {isLoading ? (
        <div className="ledger-surface p-5">
          <SkeletonRows rows={4} />
        </div>
      ) : all.length === 0 ? (
        <EmptyState
          title={viewStatus === "open" ? "No open positions" : "No closed positions"}
          body={
            viewStatus === "open"
              ? "Add a position above to start tracking your book."
              : "Close some positions to see them here."
          }
        />
      ) : (
        <div className="ledger-surface overflow-hidden">
          <PositionsTable positions={all} showClose={viewStatus === "open"} />
        </div>
      )}
    </main>
  );
}
