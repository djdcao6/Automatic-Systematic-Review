"use client";

import { PossibleDuplicatesPanel } from "@/components/PossibleDuplicatesPanel";
import { useReviewProject } from "@/lib/ReviewProjectContext";

export default function DuplicatesPage() {
  const { project, refreshProject } = useReviewProject();

  return (
    <main className="page">
      <PossibleDuplicatesPanel reviewProjectId={project.id} onChanged={refreshProject} />
    </main>
  );
}
