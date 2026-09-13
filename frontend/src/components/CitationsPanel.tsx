"use client";

import Link from "next/link";
import { useEffect, useState, type ChangeEvent } from "react";

import { exportReviewProject, listCitations, uploadCitations, type Citation } from "@/lib/api";

export function CitationsPanel({
  reviewProjectId,
  onCitationsChanged,
}: {
  reviewProjectId: string;
  onCitationsChanged?: () => void;
}) {
  const [citations, setCitations] = useState<Citation[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listCitations(reviewProjectId)
      .then(setCitations)
      .catch(() => setError("Failed to load citations."));
  }, [reviewProjectId]);

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      await uploadCitations(reviewProjectId, file);
      setCitations(await listCitations(reviewProjectId));
      setError(null);
      onCitationsChanged?.();
    } catch {
      setError("Failed to upload citations.");
    } finally {
      event.target.value = "";
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
      setError(null);
    } catch {
      setError("Failed to export review project.");
    }
  }

  return (
    <section>
      <h2>Citations</h2>
      {error && <p role="alert">{error}</p>}
      <label htmlFor="citation-file">Upload RIS or CSV file</label>
      <input id="citation-file" type="file" accept=".ris,.csv" onChange={handleFileChange} />
      <button type="button" onClick={handleExport}>
        Export CSV
      </button>
      <ul>
        {citations.map((citation) => (
          <li key={citation.id}>
            <Link href={`/review-projects/${reviewProjectId}/citations/${citation.id}`}>
              {citation.title}
            </Link>
            {citation.needs_abstract && <span> (needs abstract)</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}
