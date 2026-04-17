import { useState } from "react";
import html2canvas from "html2canvas";

export interface ChartCaptureButtonProps {
  targetRef: React.RefObject<HTMLElement>;
  caption?: string;
}

const STORAGE_KEY = "staged_image_ids";

function appendStaged(id: number) {
  const cur = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]") as number[];
  cur.push(id);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(cur));
}

export default function ChartCaptureButton({ targetRef, caption = "" }: ChartCaptureButtonProps) {
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");

  async function capture() {
    if (!targetRef.current) return;
    setBusy(true);
    try {
      const canvas = await html2canvas(targetRef.current);
      const blob: Blob = await new Promise((resolve, reject) =>
        canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("no blob"))), "image/png"),
      );
      const resp = await fetch("/api/snapshots/images/?staged=true", {
        method: "POST",
        headers: { "Content-Type": "image/png", "X-Caption": caption },
        body: blob,
      });
      if (!resp.ok) throw new Error(`upload failed ${resp.status}`);
      const body: { id: number } = await resp.json();
      appendStaged(body.id);
      setToast("Captured — will attach to your next snapshot.");
      setTimeout(() => setToast(""), 2500);
    } catch (e) {
      setToast(`Capture failed: ${(e as Error).message}`);
      setTimeout(() => setToast(""), 4000);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ position: "absolute", top: 8, right: 8, zIndex: 10 }}>
      <button
        type="button"
        onClick={capture}
        disabled={busy}
        style={{
          background: "rgba(20,20,20,0.7)",
          color: "#fff",
          border: "1px solid #333",
          padding: "4px 10px",
          borderRadius: 4,
          cursor: busy ? "wait" : "pointer",
        }}
      >
        {busy ? "Capturing…" : "Capture chart"}
      </button>
      {toast && (
        <div
          role="status"
          style={{ marginTop: 6, background: "rgba(20,20,20,0.85)", color: "#fff",
                   padding: "4px 8px", borderRadius: 4, fontSize: 12 }}
        >{toast}</div>
      )}
    </div>
  );
}
