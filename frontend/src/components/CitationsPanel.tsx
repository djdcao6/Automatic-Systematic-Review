"use client";

import Link from "next/link";
import { useState, type ChangeEvent } from "react";

import { listCitations, uploadCitations, type CitationUploadResult } from "@/lib/api";
import { useListResource } from "@/lib/useListResource";

export function CitationsPanel({
  reviewProjectId,
  onCitationsChanged,
}: {
  reviewProjectId: string;
  onCitationsChanged?: () => void;
}) {
  const {
    data: citations,
    error: loadError,
    loaded,
    refresh,
  } = useListResource(
    () => listCitations(reviewProjectId),
    [reviewProjectId],
    "Failed to load citations."
  );
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [skipped, setSkipped] = useState<CitationUploadResult["skipped"]>([]);
  const error = uploadError ?? loadError;

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      const result = await uploadCitations(reviewProjectId, file);
      setUploadError(null);
      setSkipped(result.skipped);
      await refresh();
      onCitationsChanged?.();
    } catch (err) {
      setSkipped([]);
      setUploadError(err instanceof Error ? err.message : "Failed to upload citations.");
    } finally {
      event.target.value = "";
    }
  }

  return (
    <section>
      <h2>Citations</h2>
      {error && <p role="alert">{error}</p>}
      {skipped.length > 0 && (
        <div role="status">
          <p>
            {skipped.length} {skipped.length === 1 ? "row" : "rows"} skipped:
          </p>
          <ul>
            {skipped.map(({ row, reason }) => (
              <li key={row}>{`Row ${row}: ${reason}`}</li>
            ))}
          </ul>
        </div>
      )}
      <label htmlFor="citation-file">Upload RIS or CSV file</label>
      <input id="citation-file" type="file" accept=".ris,.csv" onChange={handleFileChange} />
      {loaded && citations.length === 0 && (
        <p className="meta">No citations yet. Upload a RIS or CSV file above.</p>
      )}
      {citations.length > 0 && (
        <ul className="rows">
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
      )}
    </section>
  );
}
