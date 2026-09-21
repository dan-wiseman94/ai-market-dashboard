import { useId, useRef, useState, type FormEvent } from "react";
import { ApiError } from "@/api/client";
import { FILE_KINDS, FILE_TOO_LARGE_CODE, type FileKind, type UserFile } from "@/api/threads";
import { useUploadFile } from "@/hooks/useFiles";

const KIND_LABELS: Record<FileKind, string> = {
  filing: "SEC filing",
  transcript: "Earnings transcript",
  ohlc_csv: "Historical OHLC CSV",
  research: "Research PDF",
  other: "Other",
};

/**
 * Turn an upload failure into something the user can act on.
 *
 * The 413 is the one the size cap produces and it must never read as a generic
 * "Request failed": the server states the file's size and the ceiling, so quote
 * it. `no_key` is the other actionable one — the bytes go to the Anthropic Files
 * API, so an upload without a Claude key cannot work at all.
 */
// eslint-disable-next-line react-refresh/only-export-components -- pure error mapper, co-located with the form it serves
export function uploadErrorText(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.code === FILE_TOO_LARGE_CODE) {
      return `That file is over the upload limit, so it was rejected. ${err.message}`;
    }
    if (err.code === "no_key") {
      return "Uploads need a Claude API key — add one under Settings → Connections.";
    }
    if (err.code === "no_file") return "Choose a file to upload.";
    return err.message || "Upload failed.";
  }
  return "Upload failed.";
}

/**
 * Upload a document to the Files API: the file itself plus the `kind`/`ticker`
 * tags the list is filtered by.
 */
export function FileUploadForm({ onUploaded }: { onUploaded?: (file: UserFile) => void }) {
  const upload = useUploadFile();
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState<FileKind>("research");
  const [ticker, setTicker] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [uploaded, setUploaded] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const baseId = useId();
  const fileId = `${baseId}-file`;
  const fileHintId = `${baseId}-file-hint`;
  const kindId = `${baseId}-kind`;
  const tickerId = `${baseId}-ticker`;
  const tickerHintId = `${baseId}-ticker-hint`;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!file) {
      setError("Choose a file to upload.");
      return;
    }
    setError(null);
    setUploaded(null);
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    const sym = ticker.trim().toUpperCase();
    if (sym) form.append("ticker", sym);
    upload.mutate(form, {
      onSuccess: (created) => {
        setUploaded(created.filename || file.name);
        setFile(null);
        setTicker("");
        if (fileInput.current) fileInput.current.value = "";
        onUploaded?.(created);
      },
      onError: (err) => setError(uploadErrorText(err)),
    });
  };

  return (
    <form onSubmit={submit} data-testid="file-upload-form" className="mb-4">
      <fieldset disabled={upload.isPending} className="flex flex-col gap-3 min-w-0">
        <legend className="ledger-eyebrow">Upload a document</legend>

        <div className="space-y-1.5">
          <label htmlFor={fileId} className="block ledger-eyebrow text-copper-400">
            File
          </label>
          <input
            id={fileId}
            ref={fileInput}
            type="file"
            aria-describedby={fileHintId}
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setError(null);
            }}
            className="block w-full font-mono text-[12px] text-ink-200 file:mr-3 file:px-2.5 file:py-1 file:rounded file:border file:border-rule-soft file:bg-ink-800 file:text-ink-100 file:font-mono file:text-[11px]"
          />
          <p id={fileHintId} className="text-[11px] text-ink-400">
            Up to 32 MB. The bytes go straight to the Anthropic Files API and are
            not stored locally, so a Claude key is required.
          </p>
        </div>

        <div className="flex flex-wrap gap-3">
          <div className="space-y-1.5">
            <label htmlFor={kindId} className="block ledger-eyebrow text-copper-400">
              Kind
            </label>
            <select
              id={kindId}
              value={kind}
              onChange={(e) => {
                // Narrow by lookup rather than casting the raw select value.
                const next = FILE_KINDS.find((k) => k === e.target.value);
                if (next) setKind(next);
              }}
              className="ledger-input font-mono text-[12px]"
            >
              {FILE_KINDS.map((k) => (
                <option key={k} value={k}>
                  {KIND_LABELS[k]}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <label htmlFor={tickerId} className="block ledger-eyebrow text-copper-400">
              Symbol
            </label>
            <input
              id={tickerId}
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              placeholder="AAPL"
              aria-describedby={tickerHintId}
              className="ledger-input font-mono text-[12px] w-28"
            />
            <p id={tickerHintId} className="text-[11px] text-ink-400">
              Optional — tags the file to a ticker.
            </p>
          </div>

          <button
            type="submit"
            className="ledger-ghost self-start mt-6 py-1 px-3 text-[11px] font-mono uppercase tracking-wider"
          >
            {upload.isPending ? "Uploading…" : "Upload"}
          </button>
        </div>
      </fieldset>

      {error && (
        <p role="alert" data-testid="file-upload-error" className="mt-2 text-[12px] text-loss">
          {error}
        </p>
      )}
      {uploaded && !error && (
        <p role="status" className="mt-2 text-[12px] text-ink-400">
          Uploaded {uploaded}.
        </p>
      )}
    </form>
  );
}

export default FileUploadForm;
