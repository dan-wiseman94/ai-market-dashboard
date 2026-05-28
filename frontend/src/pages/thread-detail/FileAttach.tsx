import { FileAttachPanel } from "@/components/FileAttachPanel";
import { useFiles, useAttachFileToThread } from "@/hooks/useFiles";

export default function FileAttach({ threadId }: { threadId: number }) {
  const { data: files = [] } = useFiles();
  const attach = useAttachFileToThread(threadId);
  return (
    <details className="mt-6 ledger-surface px-5 py-3">
      <summary className="cursor-pointer ledger-eyebrow">Attach a file</summary>
      <div className="mt-2">
        <FileAttachPanel
          threadId={threadId}
          files={files}
          onAttach={(fileId) =>
            attach.mutate({ fileId, prompt: "Please review this document." })
          }
        />
      </div>
    </details>
  );
}
