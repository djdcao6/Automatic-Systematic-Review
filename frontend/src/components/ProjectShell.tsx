"use client";

import { useEffect, useState, type ReactNode } from "react";

import { PageStatus } from "@/components/PageStatus";
import { ProjectRail } from "@/components/ProjectRail";
import { exportReviewProject, getMe, getReviewProject, type ReviewProjectDetail } from "@/lib/api";
import { ReviewProjectProvider } from "@/lib/ReviewProjectContext";

export function ProjectShell({
  reviewProjectId,
  children,
}: {
  reviewProjectId: string;
  children: ReactNode;
}) {
  const [loaded, setLoaded] = useState<ReviewProjectDetail | null>(null);
  const [isOwner, setIsOwner] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  // Whatever was loaded for a project the Reviewer has since left is not shown.
  const project = loaded?.id === reviewProjectId ? loaded : null;

  useEffect(() => {
    let ignore = false;
    // The rail's Owner-only links depend on who is looking, so wait for both.
    // A failed lookup only costs the Owner-only links; the project still shows.
    Promise.all([getReviewProject(reviewProjectId), getMe().catch(() => null)])
      .then(([data, reviewer]) => {
        if (ignore) return;
        setLoaded(data);
        setIsOwner(reviewer?.id === data.owner_reviewer_id);
      })
      .catch(() => {
        if (!ignore) setError("Failed to load review project.");
      });
    return () => {
      ignore = true;
    };
  }, [reviewProjectId]);

  // Called after something that can change the live counters. Best-effort: if
  // it fails, what is on screen stays, since the Reviewer's own action worked.
  async function refreshProject() {
    try {
      setLoaded(await getReviewProject(reviewProjectId));
    } catch {
      // Keep the project already on screen.
    }
  }

  async function handleExport() {
    try {
      const { blob, filename } = await exportReviewProject(reviewProjectId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setExportError(null);
    } catch {
      setExportError("Failed to export review project.");
    }
  }

  if (!project) {
    return <PageStatus error={error} />;
  }

  return (
    <ReviewProjectProvider value={{ project, isOwner, refreshProject }}>
      <div className="shell">
        <ProjectRail
          reviewProjectId={project.id}
          reviewMode={project.review_mode}
          isOwner={isOwner}
        />
        <div className="shell-main">
          <header className="page-head">
            <p className="project-name">{project.name}</p>
            <p className="meta">Review Mode: {project.review_mode}</p>
            <p className="meta">
              {project.citations_needing_decision} citation(s) still need a decision
            </p>
            <div className="actions">
              <button type="button" onClick={handleExport}>
                Export CSV
              </button>
            </div>
          </header>
          {exportError && <p role="alert">{exportError}</p>}
          {children}
        </div>
      </div>
    </ReviewProjectProvider>
  );
}
