import { useParams } from "react-router-dom";
import { useThesis } from "@/hooks/useTheses";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import { ThesisMasthead } from "./thesis-detail/ThesisMasthead";
import { ThesisFields } from "./thesis-detail/ThesisFields";
import { SourceLinks } from "./thesis-detail/SourceLinks";
import { CloseThesisForm } from "./thesis-detail/CloseThesisForm";
import { PostMortemsSection } from "./thesis-detail/PostMortemsSection";

export default function ThesisDetailPage() {
  const { id } = useParams<{ id: string }>();
  const tid = id ? parseInt(id, 10) : null;
  const { data: thesis, isLoading } = useThesis(tid);

  if (isLoading) {
    return (
      <div className="max-w-3xl mx-auto p-6">
        <SkeletonRows rows={6} />
      </div>
    );
  }

  if (!thesis) {
    return (
      <div className="max-w-3xl mx-auto p-6">
        <EmptyState title="Thesis not found" body="This thesis does not exist or has been deleted." />
      </div>
    );
  }

  return (
    <main className="max-w-3xl mx-auto p-6 ledger-fade-in">
      <ThesisMasthead thesis={thesis} />
      <ThesisFields thesis={thesis} />
      <SourceLinks thesis={thesis} />
      {thesis.status === "open" && <CloseThesisForm thesisId={thesis.id} />}
      <PostMortemsSection thesisId={thesis.id} postmortems={thesis.postmortems} />
    </main>
  );
}
