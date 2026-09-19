"use client";

import { ExtractionFieldsPanel } from "@/components/ExtractionFieldsPanel";
import { useReviewProject } from "@/lib/ReviewProjectContext";

export default function ExtractionFieldsPage() {
  const { project } = useReviewProject();

  return (
    <main className="page">
      <ExtractionFieldsPanel reviewProjectId={project.id} />
    </main>
  );
}
