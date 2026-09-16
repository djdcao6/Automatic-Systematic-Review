"use client";

import { useEffect, useState, type FormEvent } from "react";

import {
  generateSearchTerms,
  getSearchTerms,
  updateSearchTerms,
  type SearchTerms,
  type SearchTermsInput,
} from "@/lib/api";

function toInput(searchTerms: SearchTerms): SearchTermsInput {
  return {
    population_terms: searchTerms.population_terms,
    intervention_terms: searchTerms.intervention_terms,
    comparison_terms: searchTerms.comparison_terms,
    outcome_terms: searchTerms.outcome_terms,
  };
}

function ConceptTerms({
  label,
  terms,
  disabled,
  onAdd,
  onRemove,
}: {
  label: string;
  terms: string[];
  disabled: boolean;
  onAdd: (term: string) => void;
  onRemove: (term: string) => void;
}) {
  const [newTerm, setNewTerm] = useState("");
  const inputId = `search-term-${label.toLowerCase()}`;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = newTerm.trim();
    if (!trimmed) return;
    onAdd(trimmed);
    setNewTerm("");
  }

  return (
    <div>
      <h3>{label}</h3>
      <ul>
        {terms.map((term) => (
          <li key={term}>
            {term}
            <button type="button" disabled={disabled} onClick={() => onRemove(term)}>
              Remove
            </button>
          </li>
        ))}
      </ul>
      <form onSubmit={handleSubmit}>
        <label htmlFor={inputId}>Add {label} term</label>
        <input
          id={inputId}
          value={newTerm}
          disabled={disabled}
          onChange={(event) => setNewTerm(event.target.value)}
        />
        <button type="submit" disabled={disabled}>
          Add
        </button>
      </form>
    </div>
  );
}

export function SearchTermsPanel({ reviewProjectId }: { reviewProjectId: string }) {
  const [searchTerms, setSearchTerms] = useState<SearchTerms | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Add/remove build their PUT payload off this state, so a second edit fired
  // before the first request resolves would read a stale snapshot and its
  // response could overwrite the first edit. Disabling the controls while a
  // request is in flight serializes edits and avoids that race.
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    getSearchTerms(reviewProjectId)
      .then(setSearchTerms)
      .catch(() => setError("Failed to load search terms."));
  }, [reviewProjectId]);

  async function handleGenerate() {
    setIsSaving(true);
    try {
      setSearchTerms(await generateSearchTerms(reviewProjectId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate search terms.");
    } finally {
      setIsSaving(false);
    }
  }

  async function persist(next: SearchTermsInput) {
    setIsSaving(true);
    try {
      setSearchTerms(await updateSearchTerms(reviewProjectId, next));
      setError(null);
    } catch {
      setError("Failed to update search terms.");
    } finally {
      setIsSaving(false);
    }
  }

  function handleAdd(concept: keyof SearchTermsInput, term: string) {
    if (!searchTerms) return;
    persist({ ...toInput(searchTerms), [concept]: [...searchTerms[concept], term] });
  }

  function handleRemove(concept: keyof SearchTermsInput, term: string) {
    if (!searchTerms) return;
    persist({
      ...toInput(searchTerms),
      [concept]: searchTerms[concept].filter((existing) => existing !== term),
    });
  }

  return (
    <section>
      <h2>Search Terms</h2>
      {error && <p role="alert">{error}</p>}
      <button type="button" disabled={isSaving} onClick={handleGenerate}>
        {searchTerms ? "Regenerate" : "Suggest search terms"}
      </button>

      {searchTerms && (
        <>
          <ConceptTerms
            label="Population"
            terms={searchTerms.population_terms}
            disabled={isSaving}
            onAdd={(term) => handleAdd("population_terms", term)}
            onRemove={(term) => handleRemove("population_terms", term)}
          />
          <ConceptTerms
            label="Intervention"
            terms={searchTerms.intervention_terms}
            disabled={isSaving}
            onAdd={(term) => handleAdd("intervention_terms", term)}
            onRemove={(term) => handleRemove("intervention_terms", term)}
          />
          <ConceptTerms
            label="Comparison"
            terms={searchTerms.comparison_terms}
            disabled={isSaving}
            onAdd={(term) => handleAdd("comparison_terms", term)}
            onRemove={(term) => handleRemove("comparison_terms", term)}
          />
          <ConceptTerms
            label="Outcome"
            terms={searchTerms.outcome_terms}
            disabled={isSaving}
            onAdd={(term) => handleAdd("outcome_terms", term)}
            onRemove={(term) => handleRemove("outcome_terms", term)}
          />
          <p>Combined query: {searchTerms.combined_query || "(no terms yet)"}</p>
        </>
      )}
    </section>
  );
}
