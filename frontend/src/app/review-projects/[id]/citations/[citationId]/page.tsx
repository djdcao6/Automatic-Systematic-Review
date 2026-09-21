"use client";

import { Fragment, useEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";

import { PageStatus } from "@/components/PageStatus";
import { ScreeningFolio } from "@/components/ScreeningFolio";
import {
  fetchFullTextFile,
  generateFullTextSuggestion,
  generateSuggestion,
  getCitation,
  recordExtractionValue,
  recordFullTextDecision,
  recordScreeningDecision,
  uploadFullText,
  type CitationDetail,
  type Decision,
  type FullTextSuggestionOutcome,
  type ReviewProjectDetail,
  type SuggestionOutcome,
} from "@/lib/api";
import { useReviewProject } from "@/lib/ReviewProjectContext";
import { useInFlightWrites } from "@/lib/useInFlightWrites";
import { useScreeningShortcuts } from "@/lib/useScreeningShortcuts";

const DECISIONS: Decision[] = ["include", "exclude", "maybe"];

// The key that picks each screening decision. Shown as a keycap on the choice
// (CSS reads data-key) and announced through aria-keyshortcuts.
const DECISION_KEYS: Record<Decision, string> = { include: "i", exclude: "e", maybe: "m" };

// Each choice carries a glyph (via CSS, keyed on data-decision) so colour is
// never the only signal for Include / Exclude / Maybe.
function DecisionChoices({
  name,
  value,
  onChange,
  shortcuts = false,
}: {
  name: string;
  value: Decision | null;
  onChange: (decision: Decision) => void;
  shortcuts?: boolean;
}) {
  return (
    <div className="choices">
      {DECISIONS.map((option) => (
        <label
          key={option}
          className="choice"
          data-decision={option}
          data-key={shortcuts ? DECISION_KEYS[option].toUpperCase() : undefined}
        >
          <input
            type="radio"
            name={name}
            value={option}
            checked={value === option}
            onChange={() => onChange(option)}
            aria-keyshortcuts={shortcuts ? DECISION_KEYS[option] : undefined}
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
  // Only ever set by the page itself, when it cannot read the state after an upload.
  state_unreadable:
    "Could not check for a Full-Text Suggestion. Reload the page to try again.",
};

function blankOrValue(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

// A decision and its reason, as sent to the server.
type Answer = { decision: Decision; reason: string | null };

function sameAnswer(a: Answer | null, b: Answer | null): boolean {
  return a !== null && b !== null && a.decision === b.decision && a.reason === b.reason;
}

// The keys of the writes on this page, for the one-at-a-time guard.
const SCREENING_WRITE = "screening";
const FULL_TEXT_DECISION_WRITE = "full-text-decision";
const UPLOAD = "upload";
const REFRESH = "refresh";
const EXTRACTION_PREFIX = "extraction:";
const extractionWrite = (fieldId: string) => `${EXTRACTION_PREFIX}${fieldId}`;
const isScreeningWrite = (key: string) => key === SCREENING_WRITE;
const isFullTextDecisionWrite = (key: string) => key === FULL_TEXT_DECISION_WRITE;
const isExtractionWrite = (key: string) => key.startsWith(EXTRACTION_PREFIX);
const isUpload = (key: string) => key === UPLOAD;
// Replacing the PDF invalidates the AI output the Reviewer is reading beside these
// values, so neither runs while the other does.
const isValueWrite = (key: string) => isFullTextDecisionWrite(key) || isExtractionWrite(key);

// Moving between citations changes the route params but keeps this component
// mounted. The project comes from the shell around it, loaded once for every
// section, and each citation gets a fresh body with `key` so no form state
// leaks from the last one.
export default function CitationScreeningPage({
  params,
}: {
  params: Promise<{ id: string; citationId: string }>;
}) {
  const { project, isOwner, refreshProject } = useReviewProject();
  const [citationId, setCitationId] = useState<string | null>(null);

  useEffect(() => {
    params.then((resolved) => setCitationId(resolved.citationId));
  }, [params]);

  if (!citationId) return <PageStatus />;

  return (
    <main>
      <CitationScreening
        key={citationId}
        reviewProjectId={project.id}
        citationId={citationId}
        project={project}
        isOwner={isOwner}
        onDecisionRecorded={refreshProject}
      />
    </main>
  );
}

function CitationScreening({
  reviewProjectId,
  citationId,
  project,
  isOwner,
  onDecisionRecorded,
}: {
  reviewProjectId: string;
  citationId: string;
  project: ReviewProjectDetail;
  isOwner: boolean;
  onDecisionRecorded: () => void;
}) {
  const [citation, setCitation] = useState<CitationDetail | null>(null);
  // What generating the AI suggestion produced, once it has. Until then the
  // margin shows a placeholder, so the abstract and form never wait on the model.
  const [suggestionOutcome, setSuggestionOutcome] = useState<SuggestionOutcome | null>(null);
  // The same for the Full-Text Suggestion, which is asked for once a Full Text
  // has been parsed and never fills a field the Reviewer owns.
  const [fullTextOutcome, setFullTextOutcome] = useState<FullTextSuggestionOutcome | null>(null);
  // Nothing is chosen until the Reviewer chooses: with keyboard shortcuts, a
  // pre-selected Maybe could be recorded by one stray Ctrl+Enter.
  const [decision, setDecision] = useState<Decision | null>(null);
  const [needsChoice, setNeedsChoice] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  // What the server last confirmed for each thing the Reviewer writes, kept apart from
  // the draft in the form. "Saved" is only ever said while the two are the same, so it
  // goes the moment the Reviewer edits, by click, shortcut or "Use".
  const [confirmedScreening, setConfirmedScreening] = useState<Answer | null>(null);
  // The decision was recorded but reading the Citation again failed, which is not the
  // same as the save failing.
  const [refreshFailed, setRefreshFailed] = useState(false);
  const [fullTextError, setFullTextError] = useState<string | null>(null);
  // One write at a time per form or value, and no PDF replacement alongside one.
  const writes = useInFlightWrites();
  const [viewFullTextError, setViewFullTextError] = useState<string | null>(null);
  // Nothing is chosen until the Reviewer chooses, and the AI never fills it: a
  // Save with a pre-selected answer would record a decision nobody made.
  const [ftDecision, setFtDecision] = useState<Decision | null>(null);
  const [needsFtChoice, setNeedsFtChoice] = useState(false);
  const [ftReason, setFtReason] = useState("");
  // A Full-Text Exclude needs a reason, so PRISMA can itemize the exclusions (#66).
  const [needsFtReason, setNeedsFtReason] = useState(false);
  const [ftError, setFtError] = useState<string | null>(null);
  const [confirmedFullText, setConfirmedFullText] = useState<Answer | null>(null);
  const [extractionInputs, setExtractionInputs] = useState<Record<string, string>>({});
  const [extractionErrors, setExtractionErrors] = useState<Record<string, string>>({});
  const [confirmedExtraction, setConfirmedExtraction] = useState<Record<string, string>>({});
  const formRef = useRef<HTMLFormElement>(null);

  const criteria = project.criteria;
  const exclusionRules = criteria?.exclusion_rules ?? [];
  const reviewMode = project.review_mode;

  function chooseDecision(option: Decision) {
    // The keys are live while the form is locked for a write, and a choice made then
    // would be one nobody saved.
    if (writes.isRunning(isScreeningWrite)) return;
    setDecision(option);
    setNeedsChoice(false);
  }

  useScreeningShortcuts({
    ...Object.fromEntries(
      DECISIONS.map((option) => [DECISION_KEYS[option], () => chooseDecision(option)])
    ),
    "mod+enter": () => formRef.current?.requestSubmit(),
  });

  useEffect(() => {
    getCitation(reviewProjectId, citationId)
      .then((data) => {
        setCitation(data);
        // Only the Reviewer's own recorded decision fills the form. The AI
        // suggestion stays in the margin, in pencil, however it arrives.
        if (data.screening_decision) {
          setDecision(data.screening_decision.decision);
          setReason(data.screening_decision.reason ?? "");
        }
        if (data.full_text_decision) {
          setFtDecision(data.full_text_decision.decision);
          setFtReason(data.full_text_decision.reason ?? "");
        }

        // Only the Reviewer's own recorded values fill the inputs. A suggested
        // value waits beside its field until the Reviewer uses it.
        const recordedByField = new Map(
          data.extraction_values.map((value) => [value.extraction_field_id, value.value])
        );
        const initialInputs: Record<string, string> = {};
        for (const field of data.extraction_fields) {
          initialInputs[field.id] = recordedByField.get(field.id) ?? "";
        }
        setExtractionInputs(initialInputs);
      })
      .catch(() => setError("Failed to load citation."));
  }, [reviewProjectId, citationId]);

  const needsSuggestion = citation?.suggestion_needs_generation ?? false;
  // The request for this Citation's suggestion while it is in flight, so there
  // is only ever one, however many times the effect below runs.
  const generation = useRef<Promise<void> | null>(null);

  useEffect(() => {
    if (!needsSuggestion || generation.current) return;

    const request = (): Promise<void> =>
      generateSuggestion(reviewProjectId, citationId)
        .catch(
          (): SuggestionOutcome => ({
            suggestion: null,
            suggestion_unavailable_reason: "generation_failed",
          })
        )
        .then(async (outcome) => {
          if (outcome.suggestion !== null || outcome.suggestion_unavailable_reason !== null) {
            generation.current = null;
            setSuggestionOutcome(outcome);
            return;
          }
          // A blind Reviewer is always answered with nothing, and may have
          // recorded their decision while this was in flight, so look again.
          const refreshed = await getCitation(reviewProjectId, citationId).catch(() => null);
          generation.current = null;
          if (!refreshed) return;
          setCitation(refreshed);
          // If it failed while they were blind and they can now be told, ask
          // once more. A Reviewer who can see is never answered with nothing,
          // so this cannot loop.
          if (refreshed.suggestion_needs_generation && !refreshed.screening_blind) {
            generation.current = request();
          }
        });

    generation.current = request();
  }, [needsSuggestion, reviewProjectId, citationId]);

  const needsFullTextSuggestion = citation?.full_text_suggestion_needs_generation ?? false;
  // The request for this Citation's Full-Text Suggestion while it is in flight.
  const fullTextGeneration = useRef<Promise<void> | null>(null);
  // Counts Full Text uploads. An answer asked for before the latest upload is
  // about a PDF that is gone, so it is dropped. `fullTextRound` re-runs the
  // effect below once an upload has finished, since a suggestion can be needed
  // both before and after it.
  const fullTextEpoch = useRef(0);
  const [fullTextRound, setFullTextRound] = useState(0);

  useEffect(() => {
    if (!needsFullTextSuggestion || fullTextGeneration.current) return;

    const request = (): Promise<void> => {
      const epoch = fullTextEpoch.current;
      return generateFullTextSuggestion(reviewProjectId, citationId)
        .catch(
          (): FullTextSuggestionOutcome => ({
            suggestion: null,
            suggestion_unavailable_reason: "generation_failed",
          })
        )
        .then(async (outcome) => {
          if (epoch !== fullTextEpoch.current) return;
          if (outcome.suggestion !== null || outcome.suggestion_unavailable_reason !== null) {
            fullTextGeneration.current = null;
            setFullTextOutcome(outcome);
            return;
          }
          // Nothing was kept: the Full Text was replaced while the model was
          // reading the old one. Look at the Citation again, and ask once more
          // if a suggestion is still needed.
          const refreshed = await getCitation(reviewProjectId, citationId).catch(() => null);
          fullTextGeneration.current = null;
          if (!refreshed) {
            setFullTextOutcome({ suggestion: null, suggestion_unavailable_reason: "generation_failed" });
            return;
          }
          setCitation(refreshed);
          if (refreshed.full_text_suggestion_needs_generation) {
            fullTextGeneration.current = request();
          }
        });
    };

    fullTextGeneration.current = request();
  }, [needsFullTextSuggestion, reviewProjectId, citationId, fullTextRound]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!decision) {
      setNeedsChoice(true);
      return;
    }

    await writes.run(SCREENING_WRITE, async () => {
      // That message is about the last write; this is a new one.
      setRefreshFailed(false);
      const answer: Answer = { decision, reason: blankOrValue(reason) };
      try {
        await recordScreeningDecision(reviewProjectId, citationId, answer);
      } catch {
        setError("Failed to save screening decision.");
        return;
      }
      setConfirmedScreening(answer);
      setError(null);
      onDecisionRecorded();
      await refreshCitation();
    });
  }

  // Recording a decision can flip this Reviewer from blind to revealed (#27),
  // which changes more than just screening_decision — the AI Suggestion and the
  // peer's decision may now be visible too — so the whole Citation is re-fetched
  // rather than merging the one field. If that read fails the decision is still
  // saved, so it is reported as its own problem, with a way to try the read again.
  async function refreshCitation() {
    try {
      setCitation(await getCitation(reviewProjectId, citationId));
      setRefreshFailed(false);
    } catch {
      setRefreshFailed(true);
    }
  }

  async function handleFullTextDecisionSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (writes.isRunning(isUpload)) return;
    if (!ftDecision) {
      setNeedsFtChoice(true);
      return;
    }
    const ftReasonToSave = ftDecision === "exclude" ? blankOrValue(ftReason) : null;
    if (ftDecision === "exclude" && ftReasonToSave === null) {
      setNeedsFtReason(true);
      return;
    }

    await writes.run(FULL_TEXT_DECISION_WRITE, async () => {
      const answer: Answer = { decision: ftDecision, reason: ftReasonToSave };
      try {
        const updated = await recordFullTextDecision(reviewProjectId, citationId, answer);
        setCitation((current) =>
          current ? { ...current, full_text_decision: updated } : current
        );
        setConfirmedFullText(answer);
        setFtError(null);
      } catch {
        setFtError("Failed to save full-text decision.");
      }
    });
  }

  async function handleSaveExtractionValue(fieldId: string) {
    if (writes.isRunning(isUpload)) return;
    const value = extractionInputs[fieldId] ?? "";

    await writes.run(extractionWrite(fieldId), async () => {
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
        setConfirmedExtraction((current) => ({ ...current, [fieldId]: value }));
      } catch {
        setExtractionErrors((current) => ({
          ...current,
          [fieldId]: "Failed to save extraction value.",
        }));
      }
    });
  }

  async function handleViewFullText() {
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
    if (!file) return;
    if (writes.isRunning(isValueWrite)) return;

    await writes.run(UPLOAD, async () => {
      setFullTextError(null);
      // Anything asked for from here on is about the new PDF; an answer already
      // on its way is about the old one.
      fullTextEpoch.current += 1;
      try {
        const updated = await uploadFullText(reviewProjectId, citationId, file);
        setCitation((current) => (current ? { ...current, full_text: updated } : current));
        // A new PDF clears the old Full-Text Suggestion, and only the backend
        // knows whether a new one is needed, so read that state again instead of
        // leaving a stale suggestion on the page.
        const refreshed = await getCitation(reviewProjectId, citationId).catch(() => null);
        setFullTextOutcome(null);
        setCitation((current) =>
          current
            ? {
                ...current,
                full_text_suggestion: refreshed?.full_text_suggestion ?? null,
                full_text_suggestion_unavailable_reason: refreshed
                  ? refreshed.full_text_suggestion_unavailable_reason
                  : "state_unreadable",
                full_text_suggestion_needs_generation:
                  refreshed?.full_text_suggestion_needs_generation ?? false,
              }
            : current
        );
      } catch {
        setFullTextError("Failed to upload Full Text.");
      } finally {
        // The request that was in flight, if any, now belongs to the old PDF.
        // Letting go of it and starting a new round asks again if one is needed.
        fullTextGeneration.current = null;
        setFullTextRound((round) => round + 1);
      }
    });
  }

  if (!citation) {
    return error ? <p role="alert">{error}</p> : <p className="meta">Loading...</p>;
  }

  const suggestion = citation.suggestion ?? suggestionOutcome?.suggestion ?? null;
  const unavailableReason =
    citation.suggestion_unavailable_reason ??
    suggestionOutcome?.suggestion_unavailable_reason ??
    null;
  const unavailableMessage = unavailableReason
    ? (UNAVAILABLE_MESSAGES[unavailableReason] ?? "No AI Suggestion is available for this citation.")
    : null;
  const suggestionPending = citation.suggestion_needs_generation && suggestionOutcome === null;

  const fullTextSuggestion = citation.full_text_suggestion ?? fullTextOutcome?.suggestion ?? null;
  const fullTextUnavailableReason =
    citation.full_text_suggestion_unavailable_reason ??
    fullTextOutcome?.suggestion_unavailable_reason ??
    null;
  const fullTextSuggestionUnavailableMessage = fullTextUnavailableReason
    ? (FULL_TEXT_SUGGESTION_UNAVAILABLE_MESSAGES[fullTextUnavailableReason] ??
      "No Full-Text Suggestion is available for this citation.")
    : null;
  const fullTextSuggestionPending =
    citation.full_text_suggestion_needs_generation && fullTextOutcome === null;

  const suggestedValueByField = new Map(
    (fullTextSuggestion?.extraction_values ?? []).map((value) => [
      value.extraction_field_id,
      value.value,
    ])
  );

  const conflictHeld =
    citation.screening_decision !== null &&
    citation.peer_screening_decision !== null &&
    citation.screening_decision.decision !== citation.peer_screening_decision.decision &&
    !citation.screening_resolved;

  // Saved only while the form still holds what the server confirmed.
  const screeningSaved = sameAnswer(
    confirmedScreening,
    decision ? { decision, reason: blankOrValue(reason) } : null
  );
  const fullTextSaved = sameAnswer(
    confirmedFullText,
    ftDecision
      ? { decision: ftDecision, reason: ftDecision === "exclude" ? blankOrValue(ftReason) : null }
      : null
  );
  const screeningLocked = writes.isPending(isScreeningWrite);
  const fullTextDecisionLocked = writes.isPending(isFullTextDecisionWrite);
  const uploading = writes.isPending(isUpload);
  const valueWriting = writes.isPending(isValueWrite);

  const pico = criteria
    ? [
        ["Population", criteria.population],
        ["Intervention", criteria.intervention],
        ["Comparison", criteria.comparison],
        ["Outcome", criteria.outcome],
      ].filter(([, value]) => value)
    : [];

  const byline = [citation.authors.join(", "), citation.year].filter(Boolean).join(" · ");

  const citationHref = (id: string | null) =>
    id ? `/review-projects/${reviewProjectId}/citations/${id}` : null;

  return (
    <>
      {citation.position !== null && (
        <ScreeningFolio
          position={citation.position}
          total={citation.total}
          decided={citation.total - project.citations_needing_decision}
          modeNote={project.review_mode === "dual" ? "Dual review" : "Solo review"}
          previousHref={citationHref(citation.previous_citation_id)}
          nextHref={citationHref(citation.next_citation_id)}
        />
      )}
      <div className="reading">
        <article className="reading-page">
          <p className="cit-meta">
            {citation.source.length > 0 && <span>{citation.source.join(", ")}</span>}
            {citation.needs_abstract && <span className="flag">No abstract</span>}
          </p>
          <h1>{citation.title}</h1>
          {byline && <p className="cit-byline">{byline}</p>}
          {error && <p role="alert">{error}</p>}
          <p className={citation.abstract ? "abstract" : "abstract empty"}>
            {citation.abstract ?? "No abstract available."}
          </p>

          <form className="decide" ref={formRef} onSubmit={handleSubmit}>
            <fieldset disabled={screeningLocked}>
              <legend>Screening Decision</legend>
              <DecisionChoices
                name="decision"
                value={decision}
                onChange={chooseDecision}
                shortcuts
              />
            </fieldset>

            <label htmlFor="decision-reason">Reason</label>
            <textarea
              id="decision-reason"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              // Read-only rather than disabled: Ctrl+Enter saves from here, and a
              // disabled field would drop focus, so the next letters typed would
              // fire the decision shortcuts instead of going into the reason.
              readOnly={screeningLocked}
            />

            <div className="form-actions">
              <button type="submit" disabled={screeningLocked}>
                Save Decision
              </button>
              <p className="hint">
                <kbd>Ctrl</kbd> + <kbd>Enter</kbd> to save
              </p>
            </div>
            {needsChoice && <p role="alert">Choose Include, Exclude or Maybe first.</p>}
          </form>
          {screeningSaved && confirmedScreening && (
            <p className="stamp" data-decision={confirmedScreening.decision}>
              Decision saved.
            </p>
          )}
          {refreshFailed && (
            <>
              <p role="alert">
                Your decision was saved, but this page could not be refreshed.
              </p>
              <button
                type="button"
                disabled={writes.isPending((key) => key === REFRESH)}
                onClick={() => void writes.run(REFRESH, refreshCitation)}
              >
                Refresh
              </button>
            </>
          )}
          {conflictHeld && (
            <p role="status">
              You and your Co-Reviewer recorded different decisions. This citation is held as a
              Conflict until the Owner resolves it.
            </p>
          )}

          <section>
            <h2>Full Text</h2>
            {citation.full_text ? (
              <>
                <p>
                  {citation.full_text.original_filename}{" "}
                  <button type="button" onClick={handleViewFullText}>
                    View / Download
                  </button>
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
              disabled={uploading || valueWriting}
            />
            {fullTextError && <p role="alert">{fullTextError}</p>}
          </section>

          {citation.full_text && (
            <section>
              <h2>Full-Text Suggestion</h2>
              {fullTextSuggestion ? (
                <div className="ai-note">
                  <p>
                    {fullTextSuggestion.decision}: {fullTextSuggestion.reason}
                  </p>
                  {fullTextSuggestion.truncated && (
                    <p>
                      Based on the start of this PDF only. It was too long to send in full.
                    </p>
                  )}
                </div>
              ) : fullTextSuggestionPending ? (
                <div className="ai-note">
                  <p role="status">Preparing a Full-Text Suggestion…</p>
                </div>
              ) : (
                <p>{fullTextSuggestionUnavailableMessage}</p>
              )}
            </section>
          )}

          {citation.extraction_fields.length > 0 && (
            <section>
              <h2>Extraction Values</h2>
              {citation.extraction_fields.map((field) => {
                const suggested = suggestedValueByField.get(field.id);
                const fieldWriting = writes.isPending((key) => key === extractionWrite(field.id));
                const fieldSaved =
                  confirmedExtraction[field.id] !== undefined &&
                  confirmedExtraction[field.id] === (extractionInputs[field.id] ?? "");
                return (
                  <div key={field.id} className="extraction-field">
                    <label htmlFor={`extraction-value-${field.id}`}>{field.name}</label>
                    <input
                      id={`extraction-value-${field.id}`}
                      disabled={fieldWriting}
                      value={extractionInputs[field.id] ?? ""}
                      onChange={(event) =>
                        setExtractionInputs((current) => ({
                          ...current,
                          [field.id]: event.target.value,
                        }))
                      }
                    />
                    <button
                      type="button"
                      disabled={fieldWriting || uploading}
                      onClick={() => handleSaveExtractionValue(field.id)}
                    >
                      Save
                    </button>
                    {suggested !== undefined && (
                      <div className="ai-note">
                        <p>Suggested: {suggested}</p>
                        <button
                          type="button"
                          aria-label={`Use suggested ${field.name}`}
                          disabled={fieldWriting || extractionInputs[field.id] === suggested}
                          onClick={() =>
                            setExtractionInputs((current) => ({
                              ...current,
                              [field.id]: suggested,
                            }))
                          }
                        >
                          Use
                        </button>
                      </div>
                    )}
                    {extractionErrors[field.id] && (
                      <p role="alert">{extractionErrors[field.id]}</p>
                    )}
                    {fieldSaved && <p>Extraction value saved.</p>}
                  </div>
                );
              })}
            </section>
          )}

          {citation.full_text && (
            <section>
              <form onSubmit={handleFullTextDecisionSubmit}>
                <fieldset disabled={fullTextDecisionLocked}>
                  <legend>Full-Text Decision</legend>
                  <DecisionChoices
                    name="full-text-decision"
                    value={ftDecision}
                    onChange={(option) => {
                      setFtDecision(option);
                      setNeedsFtChoice(false);
                      setNeedsFtReason(false);
                    }}
                  />
                  {needsFtChoice && <p role="alert">Choose Include, Exclude or Maybe first.</p>}

                  {ftDecision === "exclude" && (
                    <>
                      <label htmlFor="full-text-decision-reason">Reason</label>
                      {exclusionRules.length > 0 ? (
                        <select
                          id="full-text-decision-reason"
                          value={ftReason}
                          onChange={(event) => {
                            setFtReason(event.target.value);
                            setNeedsFtReason(false);
                          }}
                        >
                          <option value="">Select a reason</option>
                          {exclusionRules.map((rule) => (
                            <option key={rule} value={rule}>
                              {rule}
                            </option>
                          ))}
                        </select>
                      ) : (
                        // No Exclusion Rules to pick from, and Criteria may already be
                        // locked, so the Reviewer writes the reason instead of being
                        // unable to exclude at all.
                        <input
                          id="full-text-decision-reason"
                          type="text"
                          value={ftReason}
                          onChange={(event) => {
                            setFtReason(event.target.value);
                            setNeedsFtReason(false);
                          }}
                        />
                      )}
                      {needsFtReason && <p role="alert">Give a reason for the Exclude.</p>}
                    </>
                  )}
                </fieldset>

                <div className="form-actions">
                  <button type="submit" disabled={fullTextDecisionLocked || uploading}>
                    Save Full-Text Decision
                  </button>
                </div>
              </form>
              {ftError && <p role="alert">{ftError}</p>}
              {fullTextSaved && confirmedFullText && (
                <p className="stamp" data-decision={confirmedFullText.decision}>
                  Full-text decision saved.
                </p>
              )}
            </section>
          )}
        </article>

        <aside className="margin">
          {(pico.length > 0 || exclusionRules.length > 0) && (
            <section aria-label="Criteria">
              <h2>
                Criteria
                {project.criteria_locked && <span className="lock">locked</span>}
              </h2>
              <dl>
                {pico.map(([label, value]) => (
                  <Fragment key={label}>
                    <dt>{label}</dt>
                    <dd>{value}</dd>
                  </Fragment>
                ))}
                {exclusionRules.length > 0 && (
                  <>
                    <dt>Exclude if</dt>
                    <dd>
                      <ul className="rules">
                        {exclusionRules.map((rule) => (
                          <li key={rule}>{rule}</li>
                        ))}
                      </ul>
                    </dd>
                  </>
                )}
              </dl>
            </section>
          )}

          <section>
            <h2>AI suggestion (advisory)</h2>
            {citation.screening_blind ? (
              <div className="sealed">
                <p>Hidden until you record your own Screening Decision.</p>
              </div>
            ) : suggestion ? (
              <div className="ai-note">
                <p>
                  {suggestion.decision}: {suggestion.reason}
                </p>
              </div>
            ) : unavailableMessage ? (
              <div className="ai-note">
                <p>{unavailableMessage}</p>
              </div>
            ) : suggestionPending ? (
              <div className="ai-note">
                <p role="status">Preparing an AI suggestion…</p>
              </div>
            ) : null}
          </section>

          {reviewMode === "dual" && (
            <section>
              <h2>{isOwner ? "Co-Reviewer" : "Owner"}&apos;s Decision</h2>
              {citation.screening_blind ? (
                <div className="sealed tab">
                  <p>Sealed until you record your own Screening Decision.</p>
                </div>
              ) : citation.peer_screening_decision ? (
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
    </>
  );
}
