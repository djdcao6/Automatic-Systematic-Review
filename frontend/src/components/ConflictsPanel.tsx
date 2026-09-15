"use client";

import { useEffect, useState } from "react";

import { listConflicts, resolveConflict, type Conflict, type Decision } from "@/lib/api";

type Pick = "owner" | "co_reviewer" | "custom";

function ConflictItem({
  reviewProjectId,
  conflict,
  isOwner,
  onChanged,
}: {
  reviewProjectId: string;
  conflict: Conflict;
  isOwner: boolean;
  onChanged: () => void;
}) {
  const [pick, setPick] = useState<Pick>("owner");
  const [decision, setDecision] = useState<Decision>(conflict.owner_decision.decision);
  const [reason, setReason] = useState(conflict.owner_decision.reason ?? "");
  const [error, setError] = useState<string | null>(null);

  function choose(which: "owner" | "co_reviewer") {
    setPick(which);
    const source = which === "owner" ? conflict.owner_decision : conflict.co_reviewer_decision;
    setDecision(source.decision);
    setReason(source.reason ?? "");
  }

  async function handleResolve() {
    try {
      await resolveConflict(reviewProjectId, conflict.id, {
        decision,
        reason: reason.trim().length > 0 ? reason : null,
      });
      setError(null);
      onChanged();
    } catch {
      setError("Failed to resolve conflict.");
    }
  }

  return (
    <li>
      <h3>{conflict.citation.title}</h3>
      {error && <p role="alert">{error}</p>}
      <table>
        <thead>
          <tr>
            <th>Owner</th>
            <th>Co-Reviewer</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>
              {conflict.owner_decision.decision}
              {conflict.owner_decision.reason ? `: ${conflict.owner_decision.reason}` : ""}
            </td>
            <td>
              {conflict.co_reviewer_decision.decision}
              {conflict.co_reviewer_decision.reason
                ? `: ${conflict.co_reviewer_decision.reason}`
                : ""}
            </td>
          </tr>
        </tbody>
      </table>

      {isOwner ? (
        <div>
          <label>
            <input
              type="radio"
              name={`${conflict.id}-pick`}
              checked={pick === "owner"}
              onChange={() => choose("owner")}
            />
            Use Owner&apos;s decision
          </label>
          <label>
            <input
              type="radio"
              name={`${conflict.id}-pick`}
              checked={pick === "co_reviewer"}
              onChange={() => choose("co_reviewer")}
            />
            Use Co-Reviewer&apos;s decision
          </label>
          <label>
            <input
              type="radio"
              name={`${conflict.id}-pick`}
              checked={pick === "custom"}
              onChange={() => setPick("custom")}
            />
            Enter a different decision
          </label>

          <label htmlFor={`${conflict.id}-decision`}>Final decision</label>
          <select
            id={`${conflict.id}-decision`}
            value={decision}
            onChange={(event) => {
              setPick("custom");
              setDecision(event.target.value as Decision);
            }}
          >
            <option value="include">Include</option>
            <option value="exclude">Exclude</option>
            <option value="maybe">Maybe</option>
          </select>

          <label htmlFor={`${conflict.id}-reason`}>Reason</label>
          <input
            id={`${conflict.id}-reason`}
            value={reason}
            onChange={(event) => {
              setPick("custom");
              setReason(event.target.value);
            }}
          />

          <button type="button" onClick={handleResolve}>
            Resolve
          </button>
        </div>
      ) : (
        <p>Waiting for the Owner to resolve this Conflict.</p>
      )}
    </li>
  );
}

export function ConflictsPanel({
  reviewProjectId,
  isOwner,
  onChanged,
}: {
  reviewProjectId: string;
  isOwner: boolean;
  onChanged?: () => void;
}) {
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listConflicts(reviewProjectId)
      .then(setConflicts)
      .catch(() => setError("Failed to load conflicts."));
  }, [reviewProjectId]);

  async function refresh() {
    try {
      setConflicts(await listConflicts(reviewProjectId));
      setError(null);
    } catch {
      setError("Failed to load conflicts.");
    }
    onChanged?.();
  }

  return (
    <section>
      <h2>Conflicts</h2>
      {error && <p role="alert">{error}</p>}
      {conflicts.length === 0 ? (
        <p>No outstanding Conflicts.</p>
      ) : (
        <ul>
          {conflicts.map((conflict) => (
            <ConflictItem
              key={conflict.id}
              reviewProjectId={reviewProjectId}
              conflict={conflict}
              isOwner={isOwner}
              onChanged={refresh}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
