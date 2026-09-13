"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

import {
  getCitation,
  recordScreeningDecision,
  type CitationDetail,
  type Decision,
} from "@/lib/api";

const DECISIONS: Decision[] = ["include", "exclude", "maybe"];

const UNAVAILABLE_MESSAGES: Record<string, string> = {
  missing_abstract:
    "This citation is missing an abstract, so no AI Suggestion could be generated.",
  generation_failed:
    "Generating an AI Suggestion failed. You can still record a decision manually.",
};

function blankOrValue(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export default function CitationScreeningPage({
  params,
}: {
  params: Promise<{ id: string; citationId: string }>;
}) {
  const [reviewProjectId, setReviewProjectId] = useState<string | null>(null);
  const [citationId, setCitationId] = useState<string | null>(null);
  const [citation, setCitation] = useState<CitationDetail | null>(null);
  const [decision, setDecision] = useState<Decision>("maybe");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    params.then((resolved) => {
      setReviewProjectId(resolved.id);
      setCitationId(resolved.citationId);
    });
  }, [params]);

  useEffect(() => {
    if (!reviewProjectId || !citationId) return;
    getCitation(reviewProjectId, citationId)
      .then((data) => {
        setCitation(data);
        if (data.screening_decision) {
          setDecision(data.screening_decision.decision);
          setReason(data.screening_decision.reason ?? "");
        } else if (data.suggestion) {
          setDecision(data.suggestion.decision);
          setReason(data.suggestion.reason);
        }
      })
      .catch(() => setError("Failed to load citation."));
  }, [reviewProjectId, citationId]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!reviewProjectId || !citationId) return;

    try {
      const updated = await recordScreeningDecision(reviewProjectId, citationId, {
        decision,
        reason: blankOrValue(reason),
      });
      setCitation((current) =>
        current ? { ...current, screening_decision: updated } : current
      );
      setSaved(true);
      setError(null);
    } catch {
      setError("Failed to save screening decision.");
    }
  }

  if (!citation) {
    return error ? <p role="alert">{error}</p> : <p>Loading...</p>;
  }

  const unavailableMessage = citation.suggestion_unavailable_reason
    ? (UNAVAILABLE_MESSAGES[citation.suggestion_unavailable_reason] ??
      "No AI Suggestion is available for this citation.")
    : null;

  return (
    <main>
      {reviewProjectId && (
        <Link href={`/review-projects/${reviewProjectId}`}>Back to project</Link>
      )}
      <h1>{citation.title}</h1>
      {error && <p role="alert">{error}</p>}
      <p>{citation.abstract ?? "No abstract available."}</p>

      <section>
        <h2>AI Suggestion</h2>
        {citation.suggestion ? (
          <p>
            {citation.suggestion.decision}: {citation.suggestion.reason}
          </p>
        ) : (
          <p>{unavailableMessage}</p>
        )}
      </section>

      <form onSubmit={handleSubmit}>
        <fieldset>
          <legend>Screening Decision</legend>
          {DECISIONS.map((option) => (
            <label key={option}>
              <input
                type="radio"
                name="decision"
                value={option}
                checked={decision === option}
                onChange={() => setDecision(option)}
              />
              {option}
            </label>
          ))}
        </fieldset>

        <label htmlFor="decision-reason">Reason</label>
        <textarea
          id="decision-reason"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />

        <button type="submit">Save Decision</button>
      </form>
      {saved && <p>Decision saved.</p>}
    </main>
  );
}
