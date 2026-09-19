"use client";

import { ConflictsPanel } from "@/components/ConflictsPanel";
import { SectionUnavailable } from "@/components/SectionUnavailable";
import { useReviewProject } from "@/lib/ReviewProjectContext";

export default function ConflictsPage() {
  const { project, isOwner, refreshProject } = useReviewProject();

  if (project.review_mode !== "dual") {
    return <SectionUnavailable />;
  }

  return (
    <main className="page">
      <ConflictsPanel reviewProjectId={project.id} isOwner={isOwner} onChanged={refreshProject} />
    </main>
  );
}
