"use client";

import { useEffect, useState } from "react";

import {
  dismissPossibleDuplicate,
  listPossibleDuplicates,
  resolvePossibleDuplicate,
  type ConflictField,
  type ConflictResolutionChoiceInput,
  type ConflictWinner,
  type PossibleDuplicate,
  type PossibleDuplicateCitation,
} from "@/lib/api";

function conflictKey(field: ConflictField): string {
  return `${field.field}:${field.extraction_field_id ?? ""}`;
}

function fieldLabel(field: ConflictField): string {
  switch (field.field) {
    case "screening_decision":
      return "Screening Decision";
    case "full_text_decision":
      return "Full-Text Decision";
    case "full_text":
      return "Full Text";
    case "extraction_value":
      return field.extraction_field_name ?? "Extraction Value";
  }
}

function valueLabel(field: ConflictField, citation: PossibleDuplicateCitation): string {
  if (field.field === "screening_decision") {
    return citation.screening_decision?.decision ?? "—";
  }
  if (field.field === "full_text_decision") {
    return citation.full_text_decision?.decision ?? "—";
  }
  if (field.field === "full_text") {
    return citation.full_text?.original_filename ?? "—";
  }
  const value = citation.extraction_values.find(
    (candidate) => candidate.extraction_field_id === field.extraction_field_id
  );
  return value?.value ?? "—";
}

function PossibleDuplicateItem({
  reviewProjectId,
  possibleDuplicate,
  onChanged,
}: {
  reviewProjectId: string;
  possibleDuplicate: PossibleDuplicate;
  onChanged: () => void;
}) {
  const [choices, setChoices] = useState<Record<string, ConflictWinner>>(() =>
    Object.fromEntries(
      possibleDuplicate.conflicting_fields.map((field) => [conflictKey(field), "survivor" as const])
    )
  );
  const [error, setError] = useState<string | null>(null);

  function setChoice(field: ConflictField, winner: ConflictWinner) {
    setChoices((previous) => ({ ...previous, [conflictKey(field)]: winner }));
  }

  async function handleResolve() {
    const payload: ConflictResolutionChoiceInput[] = possibleDuplicate.conflicting_fields.map(
      (field) => ({
        field: field.field,
        extraction_field_id: field.extraction_field_id,
        winner: choices[conflictKey(field)],
      })
    );

    try {
      await resolvePossibleDuplicate(reviewProjectId, possibleDuplicate.id, payload);
      setError(null);
      onChanged();
    } catch {
      setError("Failed to resolve possible duplicate.");
    }
  }

  async function handleDismiss() {
    try {
      await dismissPossibleDuplicate(reviewProjectId, possibleDuplicate.id);
      setError(null);
      onChanged();
    } catch {
      setError("Failed to dismiss possible duplicate.");
    }
  }

  return (
    <li>
      <h3>{possibleDuplicate.survivor.title}</h3>
      {error && <p role="alert">{error}</p>}
      <table>
        <thead>
          <tr>
            <th>Field</th>
            <th>Citation A</th>
            <th>Citation B</th>
          </tr>
        </thead>
        <tbody>
          {possibleDuplicate.conflicting_fields.map((field) => {
            const key = conflictKey(field);
            const groupName = `${possibleDuplicate.id}-${key}`;
            return (
              <tr key={key}>
                <td>{fieldLabel(field)}</td>
                <td>
                  <label>
                    <input
                      type="radio"
                      name={groupName}
                      checked={choices[key] === "survivor"}
                      onChange={() => setChoice(field, "survivor")}
                    />
                    {valueLabel(field, possibleDuplicate.survivor)}
                  </label>
                </td>
                <td>
                  <label>
                    <input
                      type="radio"
                      name={groupName}
                      checked={choices[key] === "loser"}
                      onChange={() => setChoice(field, "loser")}
                    />
                    {valueLabel(field, possibleDuplicate.loser)}
                  </label>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <button type="button" onClick={handleResolve}>
        Resolve
      </button>
      <button type="button" onClick={handleDismiss}>
        Dismiss
      </button>
    </li>
  );
}

export function PossibleDuplicatesPanel({
  reviewProjectId,
  onChanged,
}: {
  reviewProjectId: string;
  onChanged?: () => void;
}) {
  const [possibleDuplicates, setPossibleDuplicates] = useState<PossibleDuplicate[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listPossibleDuplicates(reviewProjectId)
      .then(setPossibleDuplicates)
      .catch(() => setError("Failed to load possible duplicates."));
  }, [reviewProjectId]);

  async function refresh() {
    try {
      setPossibleDuplicates(await listPossibleDuplicates(reviewProjectId));
      setError(null);
    } catch {
      setError("Failed to load possible duplicates.");
    }
    onChanged?.();
  }

  return (
    <section>
      <h2>Possible Duplicates</h2>
      {error && <p role="alert">{error}</p>}
      {possibleDuplicates.length === 0 ? (
        <p>No outstanding Possible Duplicates.</p>
      ) : (
        <ul>
          {possibleDuplicates.map((possibleDuplicate) => (
            <PossibleDuplicateItem
              key={possibleDuplicate.id}
              reviewProjectId={reviewProjectId}
              possibleDuplicate={possibleDuplicate}
              onChanged={refresh}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
