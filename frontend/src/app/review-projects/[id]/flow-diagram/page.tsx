"use client";

import { useEffect, useState } from "react";

import { FlowDiagramView } from "@/components/FlowDiagramView";
import { PageStatus } from "@/components/PageStatus";
import { getFlowDiagram, type FlowDiagram } from "@/lib/api";
import { useReviewProject } from "@/lib/ReviewProjectContext";

export default function FlowDiagramPage() {
  const { project } = useReviewProject();
  const id = project.id;
  const [diagram, setDiagram] = useState<FlowDiagram | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getFlowDiagram(id)
      .then(setDiagram)
      .catch(() => setError("Failed to load PRISMA Flow Diagram."));
  }, [id]);

  if (!diagram) {
    return <PageStatus error={error} />;
  }

  return (
    <main className="page">
      <h1>PRISMA Flow Diagram: {project.name}</h1>
      {error && <p role="alert">{error}</p>}
      <FlowDiagramView diagram={diagram} />
    </main>
  );
}
