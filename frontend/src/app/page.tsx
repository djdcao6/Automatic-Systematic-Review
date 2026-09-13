"use client";

import { type FormEvent, useEffect, useState } from "react";

import { createReviewProject, listReviewProjects, type ReviewProject } from "@/lib/api";

export default function Home() {
  const [projects, setProjects] = useState<ReviewProject[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listReviewProjects()
      .then(setProjects)
      .catch(() => setError("Failed to load review projects."));
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) return;

    try {
      const project = await createReviewProject(trimmedName);
      setProjects((current) => [...current, project]);
      setName("");
      setError(null);
    } catch {
      setError("Failed to create review project.");
    }
  }

  return (
    <main>
      <h1>Review Projects</h1>
      {error && <p role="alert">{error}</p>}
      <form onSubmit={handleSubmit}>
        <label htmlFor="project-name">Project name</label>
        <input
          id="project-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <button type="submit">Create Review Project</button>
      </form>
      <ul>
        {projects.map((project) => (
          <li key={project.id}>{project.name}</li>
        ))}
      </ul>
    </main>
  );
}
