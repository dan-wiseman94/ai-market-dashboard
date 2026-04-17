import { useState } from "react";

interface Contract {
  strike: string;
  bid?: string | null;
  ask?: string | null;
  delta?: string | null;
  iv?: string | null;
  volume?: number;
  oi?: number;
}

interface ChainPayload {
  ticker?: string;
  underlying_last: string | null;
  expiries: Record<string, { calls: Contract[]; puts: Contract[] }>;
}

export default function OptionChainTable({ payload }: { payload: ChainPayload | null }) {
  const expiryDates = payload ? Object.keys(payload.expiries).sort() : [];
  const [selected, setSelected] = useState(expiryDates[0] || "");

  if (!payload || expiryDates.length === 0) {
    return <div style={{ padding: 12, color: "#888" }}>No chain data.</div>;
  }
  const exp = payload.expiries[selected] || payload.expiries[expiryDates[0]];
  const callsByStrike = new Map(exp.calls.map((c) => [c.strike, c]));
  const putsByStrike = new Map(exp.puts.map((p) => [p.strike, p]));
  const strikes = [...new Set([...callsByStrike.keys(), ...putsByStrike.keys()])]
    .sort((a, b) => parseFloat(a) - parseFloat(b));
  const atm = payload.underlying_last ? parseFloat(payload.underlying_last) : null;

  return (
    <div style={{ padding: 8 }}>
      <div style={{ marginBottom: 8 }}>
        <strong>Underlying:</strong> {payload.underlying_last}
      </div>
      <div style={{ display: "flex", gap: 4, marginBottom: 8 }}>
        {expiryDates.map((d) => (
          <button
            key={d}
            type="button"
            onClick={() => setSelected(d)}
            style={{
              background: d === selected ? "#2a2a2a" : "#111",
              color: "#fff",
              border: "1px solid #333",
              padding: "4px 8px",
              borderRadius: 4,
              cursor: "pointer",
            }}
          >{d}</button>
        ))}
      </div>
      <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
        <thead>
          <tr style={{ borderBottom: "1px solid #333" }}>
            <th style={{ textAlign: "right" }}>call bid</th>
            <th style={{ textAlign: "right" }}>call ask</th>
            <th style={{ textAlign: "right" }}>call Δ</th>
            <th style={{ textAlign: "right" }}>call IV</th>
            <th style={{ textAlign: "center" }}>strike</th>
            <th style={{ textAlign: "right" }}>put bid</th>
            <th style={{ textAlign: "right" }}>put ask</th>
            <th style={{ textAlign: "right" }}>put Δ</th>
            <th style={{ textAlign: "right" }}>put IV</th>
          </tr>
        </thead>
        <tbody>
          {strikes.map((strike) => {
            const c = callsByStrike.get(strike) || {} as Contract;
            const p = putsByStrike.get(strike) || {} as Contract;
            const isAtm = atm !== null && Math.abs(parseFloat(strike) - atm) < 0.5;
            return (
              <tr key={strike} style={{ background: isAtm ? "#1a2a3a" : "transparent" }}>
                <td style={{ textAlign: "right" }}>{c.bid ?? "—"}</td>
                <td style={{ textAlign: "right" }}>{c.ask ?? "—"}</td>
                <td style={{ textAlign: "right" }}>{c.delta ?? "—"}</td>
                <td style={{ textAlign: "right" }}>{c.iv ?? "—"}</td>
                <td style={{ textAlign: "center", fontWeight: isAtm ? "bold" : "normal" }}>{strike}</td>
                <td style={{ textAlign: "right" }}>{p.bid ?? "—"}</td>
                <td style={{ textAlign: "right" }}>{p.ask ?? "—"}</td>
                <td style={{ textAlign: "right" }}>{p.delta ?? "—"}</td>
                <td style={{ textAlign: "right" }}>{p.iv ?? "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
