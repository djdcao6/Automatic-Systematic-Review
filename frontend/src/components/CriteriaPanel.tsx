"use client";

import { useState, type FormEvent } from "react";

import { saveCriteria, type CriteriaInput } from "@/lib/api";
import { useReviewProject } from "@/lib/ReviewProjectContext";

function toLines(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

function blankOrValue(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

export function CriteriaPanel() {
  const { project, refreshProject } = useReviewProject();
  const criteria = project.criteria;
  const [population, setPopulation] = useState(criteria?.population ?? "");
  const [intervention, setIntervention] = useState(criteria?.intervention ?? "");
  const [comparison, setComparison] = useState(criteria?.comparison ?? "");
  const [outcome, setOutcome] = useState(criteria?.outcome ?? "");
  const [exclusionRules, setExclusionRules] = useState(criteria?.exclusion_rules.join("\n") ?? "");
  const [notes, setNotes] = useState(criteria?.notes ?? "");
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const payload: CriteriaInput = {
      population: blankOrValue(population),
      intervention: blankOrValue(intervention),
      comparison: blankOrValue(comparison),
      outcome: blankOrValue(outcome),
      exclusion_rules: toLines(exclusionRules),
      notes: blankOrValue(notes),
    };

    try {
      await saveCriteria(project.id, payload);
      setError(null);
      // The form re-seeds from the shared project when the Reviewer comes back.
      await refreshProject();
    } catch {
      setError("Failed to save criteria.");
    }
  }

  return (
    <section>
      <h2>Criteria</h2>
      {error && <p role="alert">{error}</p>}
      <form onSubmit={handleSubmit} className="panel">
        <div className="field-grid">
          <div>
            <label htmlFor="population">Population</label>
            <input
              id="population"
              value={population}
              onChange={(event) => setPopulation(event.target.value)}
            />
          </div>
          <div>
            <label htmlFor="intervention">Intervention</label>
            <input
              id="intervention"
              value={intervention}
              onChange={(event) => setIntervention(event.target.value)}
            />
          </div>
          <div>
            <label htmlFor="comparison">Comparison</label>
            <input
              id="comparison"
              value={comparison}
              onChange={(event) => setComparison(event.target.value)}
            />
          </div>
          <div>
            <label htmlFor="outcome">Outcome</label>
            <input
              id="outcome"
              value={outcome}
              onChange={(event) => setOutcome(event.target.value)}
            />
          </div>
        </div>

        <label htmlFor="exclusion-rules">Exclusion rules (one per line)</label>
        <textarea
          id="exclusion-rules"
          value={exclusionRules}
          onChange={(event) => setExclusionRules(event.target.value)}
        />

        <label htmlFor="notes">Notes</label>
        <textarea id="notes" value={notes} onChange={(event) => setNotes(event.target.value)} />

        <div className="form-actions">
          <button type="submit">Save Criteria</button>
        </div>
      </form>
    </section>
  );
}
