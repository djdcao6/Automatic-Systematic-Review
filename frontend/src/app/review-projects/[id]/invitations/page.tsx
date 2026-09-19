"use client";

import { InvitationsPanel } from "@/components/InvitationsPanel";
import { SectionUnavailable } from "@/components/SectionUnavailable";
import { useReviewProject } from "@/lib/ReviewProjectContext";

export default function InvitationsPage() {
  const { project, isOwner, refreshProject } = useReviewProject();

  if (project.review_mode !== "dual" || !isOwner) {
    return <SectionUnavailable />;
  }

  return (
    <main className="page">
      <InvitationsPanel
        reviewProjectId={project.id}
        hasCoReviewer={project.co_reviewer_id !== null}
        onCoReviewerRemoved={refreshProject}
      />
    </main>
  );
}
