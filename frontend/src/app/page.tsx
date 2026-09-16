"use client";

import { type FormEvent, useEffect, useState } from "react";

import Link from "next/link";

import {
  createReviewProject,
  getMySubscription,
  listReviewProjects,
  ReviewProjectCapError,
  type MergeMode,
  type ReviewMode,
  type ReviewProject,
} from "@/lib/api";

// message and isCapError always change together (see #41's code review),
// so they're one state value rather than two that could drift out of sync.
type FormError = { message: string; isCapError: boolean };

export default function Home() {
  const [projects, setProjects] = useState<ReviewProject[]>([]);
  const [name, setName] = useState("");
  const [mergeMode, setMergeMode] = useState<MergeMode | "">("");
  const [reviewMode, setReviewMode] = useState<ReviewMode | "">("");
  const [error, setError] = useState<FormError | null>(null);
  const [billingEnabled, setBillingEnabled] = useState(false);

  useEffect(() => {
    listReviewProjects()
      .then(setProjects)
      .catch(() => setError({ message: "Failed to load review projects.", isCapError: false }));
  }, []);

  // getMySubscription 404s (resolves to null) while `billing_enabled` is
  // off, per #39's dark launch — the Account/Billing link stays hidden
  // rather than pointing at a page with nothing to show.
  useEffect(() => {
    getMySubscription()
      .then((subscription) => setBillingEnabled(subscription !== null))
      .catch(() => setBillingEnabled(false));
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName || !mergeMode || !reviewMode) return;

    try {
      const project = await createReviewProject({
        name: trimmedName,
        merge_mode: mergeMode,
        review_mode: reviewMode,
      });
      setProjects((current) => [...current, project]);
      setName("");
      setMergeMode("");
      setReviewMode("");
      setError(null);
    } catch (err) {
      if (err instanceof ReviewProjectCapError) {
        setError({ message: err.message, isCapError: true });
      } else {
        setError({ message: "Failed to create review project.", isCapError: false });
      }
    }
  }

  return (
    <main>
      <h1>Review Projects</h1>
      {billingEnabled && <Link href="/account">Account / Billing</Link>}
      {error && (
        <p role="alert">
          {error.message}
          {error.isCapError && <> <Link href="/account">Go to Account/Billing</Link></>}
        </p>
      )}
      <form onSubmit={handleSubmit}>
        <label htmlFor="project-name">Project name</label>
        <input
          id="project-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <label htmlFor="merge-mode">Merge Mode</label>
        <select
          id="merge-mode"
          value={mergeMode}
          onChange={(event) => setMergeMode(event.target.value as MergeMode | "")}
        >
          <option value="">Select a merge mode</option>
          <option value="combine">Combine</option>
          <option value="keep_first">Keep First</option>
        </select>
        <label htmlFor="review-mode">Review Mode</label>
        <select
          id="review-mode"
          value={reviewMode}
          onChange={(event) => setReviewMode(event.target.value as ReviewMode | "")}
        >
          <option value="">Select a review mode</option>
          <option value="solo">Solo</option>
          <option value="dual">Dual</option>
        </select>
        <button type="submit">Create Review Project</button>
      </form>
      <ul>
        {projects.map((project) => (
          <li key={project.id}>
            <Link href={`/review-projects/${project.id}`}>{project.name}</Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
