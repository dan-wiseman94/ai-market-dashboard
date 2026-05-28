import { useCallback } from "react";
import BranchTabs from "@/components/BranchTabs";
import CompareTotalsStrip from "@/components/CompareTotalsStrip";
import { useChannel } from "@/hooks/useChannel";
import { useBranchState, type BranchEvent } from "@/hooks/useBranchState";
import type { LiveMessage, WsMsg } from "./types";

type Props = {
  parentMsg: { id: number };
  branches: LiveMessage[];
  activeId: number | null;
  onSelect: (id: number) => void;
  threadChannel: string | null;
};

export default function BranchGroup({
  parentMsg,
  branches,
  activeId,
  onSelect,
  threadChannel,
}: Props) {
  const { state, handleEvent } = useBranchState(parentMsg.id);

  const onWsBranch = useCallback((msg: WsMsg) => {
    handleEvent(msg as BranchEvent);
  }, [handleEvent]);

  useChannel(threadChannel, onWsBranch);

  const branchTabs = branches.map((m) => ({
    id: m.id,
    label: `${state[m.id]?.provider ?? m.provider ?? "?"} / ${state[m.id]?.model ?? m.model ?? "?"}`,
    status: (state[m.id]?.status ?? (m.status === "streaming" ? "streaming" : m.status === "failed" ? "failed" : "done")) as "streaming" | "done" | "failed",
    cost: state[m.id]?.cost ?? (m.cost != null ? Number(m.cost) : undefined),
  }));

  return (
    <>
      {branchTabs.length > 0 && (
        <BranchTabs branches={branchTabs} activeId={activeId} onSelect={onSelect} />
      )}
      {branchTabs.length > 1 && <CompareTotalsStrip state={state} />}
    </>
  );
}
