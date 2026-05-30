import { useState } from "react";

// Mirrors ChartCaptureButton's html2canvas usage.
// Captures the referenced element to a PNG download.
export function SaveCardButton({
  targetRef,
  filename,
  label = "Save image",
}: {
  targetRef: React.RefObject<HTMLElement | null>;
  filename: string;
  label?: string;
}) {
  const [busy, setBusy] = useState(false);

  async function save() {
    if (!targetRef.current) return;
    setBusy(true);
    try {
      const { default: html2canvas } = await import("html2canvas");
      const canvas = await html2canvas(targetRef.current);
      const url = canvas.toDataURL("image/png");
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
    } catch {
      // Silent — never crash; caller can add a toast if desired
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      onClick={save}
      disabled={busy}
      style={{
        background: "color-mix(in srgb, var(--ink-900) 82%, transparent)",
        color: "var(--ink-100)",
        border: "1px solid var(--rule)",
        padding: "4px 10px",
        borderRadius: 4,
        cursor: busy ? "wait" : "pointer",
        fontSize: "11px",
      }}
    >
      {busy ? "Saving…" : label}
    </button>
  );
}
