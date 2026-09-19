"use client";

import { CitationsPanel } from "@/components/CitationsPanel";
import { useReviewProject } from "@/lib/ReviewProjectContext";

export default function CitationsPage() {
  const { project, refreshProject } = useReviewProject();

  return (
    <main className="page">
      <CitationsPanel reviewProjectId={project.id} onCitationsChanged={refreshProject} />
    </main>
  );
}
