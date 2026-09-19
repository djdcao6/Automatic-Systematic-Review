"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { FlowDiagramView } from "@/components/FlowDiagramView";
import { getFlowDiagram, getReviewProject, type FlowDiagram } from "@/lib/api";

export default function FlowDiagramPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const [id, setId] = useState<string | null>(null);
  const [projectName, setProjectName] = useState("");
  const [diagram, setDiagram] = useState<FlowDiagram | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    params.then((resolved) => setId(resolved.id));
  }, [params]);

  useEffect(() => {
    if (!id) return;
    getReviewProject(id)
      .then((project) => setProjectName(project.name))
      .catch(() => {
        // Best-effort; the page still works without the project's name in the heading.
      });
    getFlowDiagram(id)
      .then(setDiagram)
      .catch(() => setError("Failed to load PRISMA Flow Diagram."));
  }, [id]);

  if (!diagram) {
    return error ? <p role="alert">{error}</p> : <p>Loading...</p>;
  }

  return (
    <main className="page">
      {id && (
        <Link href={`/review-projects/${id}`} className="crumb">
          Back to project
        </Link>
      )}
      <h1>PRISMA Flow Diagram{projectName ? `: ${projectName}` : ""}</h1>
      {error && <p role="alert">{error}</p>}
      <FlowDiagramView diagram={diagram} />
    </main>
  );
}
