"use client";

import Link from "next/link";
import { Fragment, useEffect, useState, type ChangeEvent, type FormEvent } from "react";

import {
  fetchFullTextFile,
  getCitation,
  getReviewProject,
  recordExtractionValue,
  recordFullTextDecision,
  recordScreeningDecision,
  uploadFullText,
  type CitationDetail,
  type Criteria,
  type Decision,
} from "@/lib/api";

const DECISIONS: Decision[] = ["include", "exclude", "maybe"];

// Each choice carries a glyph (via CSS, keyed on data-decision) so colour is
// never the only signal for Include / Exclude / Maybe.
function DecisionChoices({
  name,
  value,
  onChange,
}: {
  name: string;
  value: Decision;
  onChange: (decision: Decision) => void;
}) {
  return (
    <div className="choices">
      {DECISIONS.map((option) => (
        <label key={option} className="choice" data-decision={option}>
          <input
            type="radio"
            name={name}
            value={option}
            checked={value === option}
            onChange={() => onChange(option)}
          />
          {option}
        </label>
      ))}
    </div>
  );
}

const UNAVAILABLE_MESSAGES: Record<string, string> = {
  missing_abstract:
    "This citation is missing an abstract, so no AI Suggestion could be generated.",
  generation_failed:
    "Generating an AI Suggestion failed. You can still record a decision manually.",
};

const FULL_TEXT_SUGGESTION_UNAVAILABLE_MESSAGES: Record<string, string> = {
  no_full_text: "Upload a Full Text to get a Full-Text Suggestion.",
  parse_failed:
    "This Full Text could not be parsed, so no Full-Text Suggestion could be generated.",
  generation_failed:
    "Generating a Full-Text Suggestion failed. You can still record a decision manually.",
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
  const [viewFullTextError, setViewFullTextError] = useState<string | null>(null);
  const [exclusionRules, setExclusionRules] = useState<string[]>([]);
  const [criteria, setCriteria] = useState<Criteria | null>(null);
  const [reviewMode, setReviewMode] = useState<"solo" | "dual">("solo");
  const [ftDecision, setFtDecision] = useState<Decision>("maybe");
  const [ftReason, setFtReason] = useState("");
  const [ftError, setFtError] = useState<string | null>(null);
  const [ftSaved, setFtSaved] = useState(false);
  const [extractionInputs, setExtractionInputs] = useState<Record<string, string>>({});
  const [extractionErrors, setExtractionErrors] = useState<Record<string, string>>({});
  const [extractionSavedFieldId, setExtractionSavedFieldId] = useState<string | null>(null);

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
        } else if (data.full_text_suggestion) {
          setFtDecision(data.full_text_suggestion.decision);
          setFtReason(data.full_text_suggestion.reason);
        }

        const suggestedByField = new Map(
          (data.full_text_suggestion?.extraction_values ?? []).map((value) => [
            value.extraction_field_id,
            value.value,
          ])
        );
        const recordedByField = new Map(
          data.extraction_values.map((value) => [value.extraction_field_id, value.value])
        );
        const initialInputs: Record<string, string> = {};
        for (const field of data.extraction_fields) {
          initialInputs[field.id] =
            recordedByField.get(field.id) ?? suggestedByField.get(field.id) ?? "";
        }
        setExtractionInputs(initialInputs);
      })
      .catch(() => setError("Failed to load citation."));
  }, [reviewProjectId, citationId]);

  useEffect(() => {
    if (!reviewProjectId) return;
    getReviewProject(reviewProjectId)
      .then((project) => {
        setExclusionRules(project.criteria?.exclusion_rules ?? []);
        setCriteria(project.criteria ?? null);
        setReviewMode(project.review_mode);
      })
      .catch(() => setExclusionRules([]));
  }, [reviewProjectId]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!reviewProjectId || !citationId) return;

    try {
      await recordScreeningDecision(reviewProjectId, citationId, {
        decision,
        reason: blankOrValue(reason),
      });
      // Recording a decision can flip this Reviewer from blind to revealed
      // (#27), which changes more than just screening_decision — the AI
      // Suggestion and the peer's decision may now be visible too — so the
      // whole Citation is re-fetched rather than merging the one field.
      const refreshed = await getCitation(reviewProjectId, citationId);
      setCitation(refreshed);
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

  async function handleSaveExtractionValue(fieldId: string) {
    if (!reviewProjectId || !citationId) return;
    const value = extractionInputs[fieldId] ?? "";

    try {
      const updated = await recordExtractionValue(reviewProjectId, citationId, fieldId, {
        value,
      });
      setCitation((current) => {
        if (!current) return current;
        const others = current.extraction_values.filter(
          (existing) => existing.extraction_field_id !== fieldId
        );
        return { ...current, extraction_values: [...others, updated] };
      });
      setExtractionErrors((current) => ({ ...current, [fieldId]: "" }));
      setExtractionSavedFieldId(fieldId);
    } catch {
      setExtractionErrors((current) => ({
        ...current,
        [fieldId]: "Failed to save extraction value.",
      }));
      setExtractionSavedFieldId(null);
    }
  }

  async function handleViewFullText() {
    if (!reviewProjectId || !citationId) return;
    setViewFullTextError(null);
    try {
      const blob = await fetchFullTextFile(reviewProjectId, citationId);
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noreferrer");
    } catch {
      setViewFullTextError("Failed to load Full Text.");
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

  const fullTextSuggestionUnavailableMessage = citation.full_text_suggestion_unavailable_reason
    ? (FULL_TEXT_SUGGESTION_UNAVAILABLE_MESSAGES[
        citation.full_text_suggestion_unavailable_reason
      ] ?? "No Full-Text Suggestion is available for this citation.")
    : null;

  const pico = criteria
    ? [
        ["Population", criteria.population],
        ["Intervention", criteria.intervention],
        ["Comparison", criteria.comparison],
        ["Outcome", criteria.outcome],
      ].filter(([, value]) => value)
    : [];

  return (
    <main>
      {reviewProjectId && (
        <Link href={`/review-projects/${reviewProjectId}`} className="crumb">
          Back to project
        </Link>
      )}
      <div className="reading">
        <article className="reading-page">
          <h1>{citation.title}</h1>
          {error && <p role="alert">{error}</p>}
          <p className={citation.abstract ? "abstract" : "abstract empty"}>
            {citation.abstract ?? "No abstract available."}
          </p>

          <form onSubmit={handleSubmit}>
            <fieldset>
              <legend>Screening Decision</legend>
              <DecisionChoices name="decision" value={decision} onChange={setDecision} />
            </fieldset>

            <label htmlFor="decision-reason">Reason</label>
            <textarea
              id="decision-reason"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />

            <div className="form-actions">
              <button type="submit">Save Decision</button>
            </div>
          </form>
          {saved && (
            <p className="stamp" data-decision={decision}>
              Decision saved.
            </p>
          )}

          <section>
            <h2>Full Text</h2>
            {citation.full_text ? (
              <>
                <p>
                  {citation.full_text.original_filename}{" "}
                  {reviewProjectId && citationId && (
                    <button type="button" onClick={handleViewFullText}>
                      View / Download
                    </button>
                  )}
                </p>
                {viewFullTextError && <p role="alert">{viewFullTextError}</p>}
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
              <h2>Full-Text Suggestion</h2>
              {citation.full_text_suggestion ? (
                <div className="ai-note">
                  <p>
                    {citation.full_text_suggestion.decision}: {citation.full_text_suggestion.reason}
                  </p>
                  {citation.full_text_suggestion.extraction_values.length > 0 && (
                    <ul>
                      {citation.full_text_suggestion.extraction_values.map((extractionValue) => (
                        <li key={extractionValue.extraction_field_id}>
                          {extractionValue.name}: {extractionValue.value}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ) : (
                <p>{fullTextSuggestionUnavailableMessage}</p>
              )}
            </section>
          )}

          {citation.extraction_fields.length > 0 && (
            <section>
              <h2>Extraction Values</h2>
              {citation.extraction_fields.map((field) => (
                <div key={field.id} className="extraction-field">
                  <label htmlFor={`extraction-value-${field.id}`}>{field.name}</label>
                  <input
                    id={`extraction-value-${field.id}`}
                    value={extractionInputs[field.id] ?? ""}
                    onChange={(event) =>
                      setExtractionInputs((current) => ({
                        ...current,
                        [field.id]: event.target.value,
                      }))
                    }
                  />
                  <button type="button" onClick={() => handleSaveExtractionValue(field.id)}>
                    Save
                  </button>
                  {extractionErrors[field.id] && (
                    <p role="alert">{extractionErrors[field.id]}</p>
                  )}
                  {extractionSavedFieldId === field.id && <p>Extraction value saved.</p>}
                </div>
              ))}
            </section>
          )}

          {citation.full_text && (
            <section>
              <form onSubmit={handleFullTextDecisionSubmit}>
                <fieldset>
                  <legend>Full-Text Decision</legend>
                  <DecisionChoices
                    name="full-text-decision"
                    value={ftDecision}
                    onChange={setFtDecision}
                  />

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

                <div className="form-actions">
                  <button type="submit">Save Full-Text Decision</button>
                </div>
              </form>
              {ftError && <p role="alert">{ftError}</p>}
              {ftSaved && (
                <p className="stamp" data-decision={ftDecision}>
                  Full-text decision saved.
                </p>
              )}
            </section>
          )}
        </article>

        <aside className="margin">
          {pico.length > 0 && (
            <section aria-label="Criteria">
              <h2>Criteria</h2>
              <dl>
                {pico.map(([label, value]) => (
                  <Fragment key={label}>
                    <dt>{label}</dt>
                    <dd>{value}</dd>
                  </Fragment>
                ))}
              </dl>
            </section>
          )}

          <section>
            <h2>AI Suggestion</h2>
            {citation.screening_blind ? (
              <div className="sealed">
                <p>Hidden until you record your own Screening Decision.</p>
              </div>
            ) : citation.suggestion ? (
              <div className="ai-note">
                <p>
                  {citation.suggestion.decision}: {citation.suggestion.reason}
                </p>
              </div>
            ) : unavailableMessage ? (
              <div className="ai-note">
                <p>{unavailableMessage}</p>
              </div>
            ) : null}
          </section>

          {reviewMode === "dual" && !citation.screening_blind && (
            <section>
              <h2>Co-Reviewer&apos;s Decision</h2>
              {citation.peer_screening_decision ? (
                <div className="ink-note">
                  <p>
                    {citation.peer_screening_decision.decision}
                    {citation.peer_screening_decision.reason
                      ? `: ${citation.peer_screening_decision.reason}`
                      : ""}
                  </p>
                </div>
              ) : (
                <div className="sealed">
                  <p>Not yet recorded.</p>
                </div>
              )}
            </section>
          )}
        </aside>
      </div>
    </main>
  );
}
