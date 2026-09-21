import { FileAttachPanel } from "@/components/FileAttachPanel";
import { FileUploadForm } from "@/components/FileUploadForm";
import { SkeletonRows } from "@/components/Skeleton";
import type { UserFile } from "@/hooks/useFiles";
import { useAttachFileToThread, useDeleteFile, useFiles } from "@/hooks/useFiles";
import { useThread } from "@/hooks/useThread";
import { useToast } from "@/hooks/useToast";

const PROVIDER_LABELS: Record<string, string> = {
  claude: "Claude",
  openai: "OpenAI",
  local: "the local endpoint",
};

function providerLabel(provider: string): string {
  return PROVIDER_LABELS[provider] ?? provider;
}

export default function FileAttach({ threadId }: { threadId: number }) {
  const { data: files = [], isLoading } = useFiles();
  // Already in the cache from the page's own useThread — this only reads the
  // thread's profile to decide whether attaching can work at all.
  const { data: thread } = useThread(threadId);
  const attach = useAttachFileToThread(threadId);
  const remove = useDeleteFile();
  const { push } = useToast();

  // Documents are Claude-only: the request builder strips the document block
  // for any other provider and the run emits a capability warning instead of
  // reading the file. Surface that here rather than offering a no-op button.
  const provider = thread?.profile?.default_provider ?? "";
  const claudeOnlyReason =
    provider && provider !== "claude"
      ? `This thread's profile runs on ${providerLabel(provider)}, which can't read attached documents — files are Claude-only.`
      : undefined;

  const handleAttach = (fileId: number) => {
    attach.mutate(
      { fileId, prompt: "Please review this document." },
      {
        onSuccess: () => push({ kind: "success", text: "File attached to the thread." }),
        onError: (err) =>
          push({ kind: "error", text: err instanceof Error ? err.message : "Attach failed." }),
      },
    );
  };

  const handleDelete = (file: UserFile) => {
    const name = file.filename || "this file";
    const ok = window.confirm(
      `Delete ${name}? This also deletes the file upstream at the provider ` +
        "(the Anthropic Files API), so any thread that already references it " +
        "loses it too. This cannot be undone.",
    );
    if (!ok) return;
    remove.mutate(file.id, {
      onSuccess: () => push({ kind: "success", text: `Deleted ${name}.` }),
      onError: (err) =>
        push({ kind: "error", text: err instanceof Error ? err.message : "Delete failed." }),
    });
  };

  return (
    <details className="mt-6 ledger-surface px-5 py-3">
      <summary className="cursor-pointer ledger-eyebrow">Attach a file</summary>
      <div className="mt-2">
        {claudeOnlyReason && (
          <p
            role="note"
            data-testid="files-claude-only"
            className="mb-3 text-[12px] text-ink-300 border border-rule-soft rounded-ledger px-3 py-2"
          >
            {claudeOnlyReason} Switch the thread&rsquo;s profile to a Claude model to use them.
          </p>
        )}
        <FileUploadForm />
        {isLoading ? (
          <SkeletonRows rows={3} />
        ) : (
          <FileAttachPanel
            threadId={threadId}
            files={files}
            onAttach={handleAttach}
            onDelete={handleDelete}
            attachDisabledReason={claudeOnlyReason}
          />
        )}
      </div>
    </details>
  );
}
