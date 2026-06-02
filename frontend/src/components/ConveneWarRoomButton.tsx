import { useNavigate } from "react-router-dom";

import type { ConveneBody } from "@/api/warroom";
import { useConveneWarRoom } from "@/hooks/useWarroom";

type Subject = Pick<ConveneBody, "thesis_id" | "coverage_note_id" | "book_snapshot_id">;

/**
 * One-click "Convene War Room" on a specific subject (thesis / coverage note /
 * book snapshot). The convene API already accepts these subject ids; this just
 * wires the button and routes to the new run's courtroom.
 */
export function ConveneWarRoomButton({
  subject,
  className,
}: {
  subject: Subject;
  className?: string;
}) {
  const navigate = useNavigate();
  const convene = useConveneWarRoom();
  return (
    <button
      type="button"
      disabled={convene.isPending}
      className={
        className ??
        "rounded border border-rule px-3 py-1 text-sm hover:bg-ink/5 disabled:opacity-50"
      }
      onClick={async () => {
        const run = await convene.mutateAsync(subject);
        navigate(`/warroom/${run.id}`);
      }}
    >
      {convene.isPending ? "Convening…" : "Convene War Room"}
    </button>
  );
}
