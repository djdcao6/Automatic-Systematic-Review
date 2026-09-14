"use client";

import Link from "next/link";
import { useEffect, useState, type ChangeEvent, type FormEvent } from "react";

import {
  fullTextFileUrl,
  getCitation,
  getReviewProject,
  recordFullTextDecision,
  recordScreeningDecision,
  uploadFullText,
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
  const [fullTextError, setFullTextError] = useState<string | null>(null);
  const [uploadingFullText, setUploadingFullText] = useState(false);
  const [exclusionRules, setExclusionRules] = useState<string[]>([]);
  const [ftDecision, setFtDecision] = useState<Decision>("maybe");
  const [ftReason, setFtReason] = useState("");
  const [ftError, setFtError] = useState<string | null>(null);
  const [ftSaved, setFtSaved] = useState(false);

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
        if (data.full_text_decision) {
          setFtDecision(data.full_text_decision.decision);
          setFtReason(data.full_text_decision.reason ?? "");
        }
      })
      .catch(() => setError("Failed to load citation."));
  }, [reviewProjectId, citationId]);

  useEffect(() => {
    if (!reviewProjectId) return;
    getReviewProject(reviewProjectId)
      .then((project) => setExclusionRules(project.criteria?.exclusion_rules ?? []))
      .catch(() => setExclusionRules([]));
  }, [reviewProjectId]);

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

  async function handleFullTextDecisionSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!reviewProjectId || !citationId) return;

    try {
      const updated = await recordFullTextDecision(reviewProjectId, citationId, {
        decision: ftDecision,
        reason: ftDecision === "exclude" ? blankOrValue(ftReason) : null,
      });
      setCitation((current) => (current ? { ...current, full_text_decision: updated } : current));
      setFtSaved(true);
      setFtError(null);
    } catch {
      setFtError("Failed to save full-text decision.");
    }
  }

  async function handleFullTextChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !reviewProjectId || !citationId) return;

    setUploadingFullText(true);
    setFullTextError(null);
    try {
      const updated = await uploadFullText(reviewProjectId, citationId, file);
      setCitation((current) => (current ? { ...current, full_text: updated } : current));
    } catch {
      setFullTextError("Failed to upload Full Text.");
    } finally {
      setUploadingFullText(false);
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

      <section>
        <h2>Full Text</h2>
        {citation.full_text ? (
          <>
            <p>
              {citation.full_text.original_filename}{" "}
              {reviewProjectId && citationId && (
                <a
                  href={fullTextFileUrl(reviewProjectId, citationId)}
                  target="_blank"
                  rel="noreferrer"
                >
                  View / Download
                </a>
              )}
            </p>
            {citation.full_text.parse_status === "parse_failed" && (
              <p role="alert">
                Could not extract text from this PDF. Enter extracted data manually.
              </p>
            )}
          </>
        ) : (
          <p>No Full Text uploaded yet.</p>
        )}
        <label htmlFor="full-text-upload">
          {citation.full_text ? "Replace Full Text" : "Upload Full Text"}
        </label>
        <input
          id="full-text-upload"
          type="file"
          accept="application/pdf"
          onChange={handleFullTextChange}
          disabled={uploadingFullText}
        />
        {fullTextError && <p role="alert">{fullTextError}</p>}
      </section>

      {citation.full_text && (
        <section>
          <form onSubmit={handleFullTextDecisionSubmit}>
            <fieldset>
              <legend>Full-Text Decision</legend>
              {DECISIONS.map((option) => (
                <label key={option}>
                  <input
                    type="radio"
                    name="full-text-decision"
                    value={option}
                    checked={ftDecision === option}
                    onChange={() => setFtDecision(option)}
                  />
                  {option}
                </label>
              ))}

              {ftDecision === "exclude" && (
                <>
                  <label htmlFor="full-text-decision-reason">Reason</label>
                  <select
                    id="full-text-decision-reason"
                    value={ftReason}
                    onChange={(event) => setFtReason(event.target.value)}
                  >
                    <option value="">Select a reason</option>
                    {exclusionRules.map((rule) => (
                      <option key={rule} value={rule}>
                        {rule}
                      </option>
                    ))}
                  </select>
                </>
              )}
            </fieldset>

            <button type="submit">Save Full-Text Decision</button>
          </form>
          {ftError && <p role="alert">{ftError}</p>}
          {ftSaved && <p>Full-text decision saved.</p>}
        </section>
      )}

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
