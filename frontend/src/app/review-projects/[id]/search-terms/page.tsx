"use client";

import { SearchTermsPanel } from "@/components/SearchTermsPanel";
import { useReviewProject } from "@/lib/ReviewProjectContext";

export default function SearchTermsPage() {
  const { project } = useReviewProject();

  return (
    <main className="page">
      <SearchTermsPanel reviewProjectId={project.id} />
    </main>
  );
}
