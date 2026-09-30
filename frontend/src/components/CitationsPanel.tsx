"use client";

import Link from "next/link";
import { useState, type ChangeEvent } from "react";

import {
  listCitations,
  uploadCitations,
  type CitationListItem,
  type CitationUploadResult,
} from "@/lib/api";
import { useListResource } from "@/lib/useListResource";

// Own decisions only (`my_screening_decision`), so in a Dual review this never depends on
// the peer's progress (ADR 0006).
function ScreeningEntry({
  reviewProjectId,
  citations,
}: {
  reviewProjectId: string;
  citations: CitationListItem[];
}) {
  const next = citations.find((citation) => citation.my_screening_decision === null);
  if (!next) {
    return <p className="meta">You have recorded a decision on every Citation.</p>;
  }
  const started = citations.some((citation) => citation.my_screening_decision !== null);
  return (
    <p>
      <Link href={`/review-projects/${reviewProjectId}/citations/${next.id}`}>
        {started ? "Continue screening" : "Start screening"}
      </Link>
    </p>
  );
}

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
    "Failed to load citations.",
  );
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [skipped, setSkipped] = useState<CitationUploadResult["skipped"]>([]);
  const [unreadableYears, setUnreadableYears] = useState<CitationUploadResult["unreadable_years"]>(
    [],
  );
  const error = uploadError ?? loadError;

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      const result = await uploadCitations(reviewProjectId, file);
      setUploadError(null);
      setSkipped(result.skipped);
      setUnreadableYears(result.unreadable_years);
      await refresh();
      onCitationsChanged?.();
    } catch (err) {
      setSkipped([]);
      setUnreadableYears([]);
      setUploadError(err instanceof Error ? err.message : "Failed to upload citations.");
    } finally {
      event.target.value = "";
    }
  }

  return (
    <section>
      <h1 className="section-title">Citations</h1>
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
      {unreadableYears.length > 0 && (
        <div role="status">
          <p>
            {unreadableYears.length} {unreadableYears.length === 1 ? "row was" : "rows were"}{" "}
            imported without a year because it could not be read:
          </p>
          <ul>
            {unreadableYears.map(({ row, value }) => (
              <li key={row}>{`Row ${row}: “${value}”`}</li>
            ))}
          </ul>
        </div>
      )}
      {loaded && citations.length > 0 && (
        <ScreeningEntry reviewProjectId={reviewProjectId} citations={citations} />
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
              {citation.my_screening_decision ? (
                <span className="decision-mark" data-decision={citation.my_screening_decision}>
                  {citation.my_screening_decision}
                </span>
              ) : (
                <span>Not yet decided</span>
              )}
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
