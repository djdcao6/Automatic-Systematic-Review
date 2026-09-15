"use client";

import Link from "next/link";
import { useEffect, useState, type ChangeEvent } from "react";

import { listCitations, uploadCitations, type Citation } from "@/lib/api";

export function CitationsPanel({
  reviewProjectId,
  onCitationsChanged,
  refreshToken,
}: {
  reviewProjectId: string;
  onCitationsChanged?: () => void;
  refreshToken?: number;
}) {
  const [citations, setCitations] = useState<Citation[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listCitations(reviewProjectId)
      .then(setCitations)
      .catch(() => setError("Failed to load citations."));
  }, [reviewProjectId, refreshToken]);

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

  return (
    <section>
      <h2>Citations</h2>
      {error && <p role="alert">{error}</p>}
      <label htmlFor="citation-file">Upload RIS or CSV file</label>
      <input id="citation-file" type="file" accept=".ris,.csv" onChange={handleFileChange} />
      <ul>
        {citations.map((citation) => (
          <li key={citation.id}>
            <Link href={`/review-projects/${reviewProjectId}/citations/${citation.id}`}>
              {citation.title}
            </Link>
            {citation.needs_abstract && <span> (needs abstract)</span>}
            {citation.blocked_pending_co_reviewer && (
              <span> (blocked: awaiting a replacement Co-Reviewer)</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
