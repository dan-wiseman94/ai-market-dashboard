import StopButton from "@/components/StopButton";
import StreamingMessage from "@/components/StreamingMessage";
import { ToolCallTrace, type ToolCallRecord } from "@/components/ToolCallTrace";
import BranchGroup from "./BranchGroup";
import type { LiveMessage } from "./types";

type Props = {
  ordered: LiveMessage[];
  branchesByParent: Record<number, LiveMessage[]>;
  toolCalls: Record<number, Record<string, ToolCallRecord>>;
  activeBranchByParent: Record<number, number>;
  onSelectBranch: (parentId: number, branchId: number) => void;
  onStop: (messageId: number) => void;
  threadChannel: string | null;
};

export default function Conversation({
  ordered,
  branchesByParent,
  toolCalls,
  activeBranchByParent,
  onSelectBranch,
  onStop,
  threadChannel,
}: Props) {
  return (
    <section className="space-y-6">
      {ordered.map((m) => {
        if (m.role === "user") {
          const children = branchesByParent[m.id] ?? [];
          const activeId = activeBranchByParent[m.id] ?? children[0]?.id ?? null;
          const active = children.find((c) => c.id === activeId) ?? children[0];
          return (
            <div key={m.id} data-testid={`message-${m.id}`} className="space-y-4">
              <StreamingMessage
                role="user" text={m.text} status={m.status}
                snapshotId={m.snapshot_id ?? null}
              />
              {children.length > 0 && (
                <div className="ledger-surface overflow-hidden">
                  <BranchGroup
                    parentMsg={m}
                    branches={children}
                    activeId={activeId}
                    onSelect={(cid) => onSelectBranch(m.id, cid)}
                    threadChannel={threadChannel}
                  />
                  {active && (
                    <div className="flex items-start gap-2 p-0">
                      <div className="flex-1 min-w-0 px-6 py-5">
                        <StreamingMessage
                          bare
                          role={active.role} text={active.text} status={active.status}
                          error={active.error} cost={active.cost} model={active.model} provider={active.provider}
                          kind={active.kind} report={active.report}
                        />
                      </div>
                      {active.status === "streaming" && (
                        <div className="pt-5 pr-4">
                          <StopButton onStop={() => onStop(active.id)} />
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        }
        const calls = Object.values(toolCalls[m.id] ?? {});
        return (
          <div key={m.id} data-testid={`message-${m.id}`} className="flex items-start gap-3">
            <div className="flex-1 min-w-0">
              <ToolCallTrace calls={calls} />
              <StreamingMessage
                role={m.role} text={m.text} status={m.status}
                error={m.error} cost={m.cost} model={m.model} provider={m.provider}
                kind={m.kind} report={m.report}
              />
            </div>
            {m.status === "streaming" && (
              <div className="pt-5">
                <StopButton onStop={() => onStop(m.id)} />
              </div>
            )}
          </div>
        );
      })}
    </section>
  );
}
