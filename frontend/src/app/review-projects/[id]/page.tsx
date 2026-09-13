"use client";

import { useEffect, useState, type FormEvent } from "react";

import { CitationsPanel } from "@/components/CitationsPanel";
import { getReviewProject, saveCriteria, type CriteriaInput, type ReviewProjectDetail } from "@/lib/api";

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

export default function ReviewProjectDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const [id, setId] = useState<string | null>(null);
  const [project, setProject] = useState<ReviewProjectDetail | null>(null);
  const [population, setPopulation] = useState("");
  const [intervention, setIntervention] = useState("");
  const [comparison, setComparison] = useState("");
  const [outcome, setOutcome] = useState("");
  const [exclusionRules, setExclusionRules] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    params.then((resolved) => setId(resolved.id));
  }, [params]);

  useEffect(() => {
    if (!id) return;
    getReviewProject(id)
      .then((data) => {
        setProject(data);
        const criteria = data.criteria;
        if (criteria) {
          setPopulation(criteria.population ?? "");
          setIntervention(criteria.intervention ?? "");
          setComparison(criteria.comparison ?? "");
          setOutcome(criteria.outcome ?? "");
          setExclusionRules(criteria.exclusion_rules.join("\n"));
          setNotes(criteria.notes ?? "");
        }
      })
      .catch(() => setError("Failed to load review project."));
  }, [id]);

  // Refreshes the live counters (e.g. citations_needing_decision) after a
  // Citations upload, without disturbing whatever the Criteria form currently
  // holds.
  async function refreshProjectCounts() {
    if (!id) return;
    try {
      setProject(await getReviewProject(id));
    } catch {
      // Best-effort refresh; the citations list itself already updated.
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!id) return;

    const payload: CriteriaInput = {
      population: blankOrValue(population),
      intervention: blankOrValue(intervention),
      comparison: blankOrValue(comparison),
      outcome: blankOrValue(outcome),
      exclusion_rules: toLines(exclusionRules),
      notes: blankOrValue(notes),
    };

    try {
      await saveCriteria(id, payload);
      setError(null);
    } catch {
      setError("Failed to save criteria.");
    }
  }

  if (!project) {
    return error ? <p role="alert">{error}</p> : <p>Loading...</p>;
  }

  return (
    <main>
      <h1>{project.name}</h1>
      <p>{project.citations_needing_decision} citation(s) still need a decision</p>
      {error && <p role="alert">{error}</p>}
      <form onSubmit={handleSubmit}>
        <label htmlFor="population">Population</label>
        <input
          id="population"
          value={population}
          onChange={(event) => setPopulation(event.target.value)}
        />

        <label htmlFor="intervention">Intervention</label>
        <input
          id="intervention"
          value={intervention}
          onChange={(event) => setIntervention(event.target.value)}
        />

        <label htmlFor="comparison">Comparison</label>
        <input
          id="comparison"
          value={comparison}
          onChange={(event) => setComparison(event.target.value)}
        />

        <label htmlFor="outcome">Outcome</label>
        <input
          id="outcome"
          value={outcome}
          onChange={(event) => setOutcome(event.target.value)}
        />

        <label htmlFor="exclusion-rules">Exclusion rules (one per line)</label>
        <textarea
          id="exclusion-rules"
          value={exclusionRules}
          onChange={(event) => setExclusionRules(event.target.value)}
        />

        <label htmlFor="notes">Notes</label>
        <textarea id="notes" value={notes} onChange={(event) => setNotes(event.target.value)} />

        <button type="submit">Save Criteria</button>
      </form>

      <CitationsPanel reviewProjectId={project.id} onCitationsChanged={refreshProjectCounts} />
    </main>
  );
}
