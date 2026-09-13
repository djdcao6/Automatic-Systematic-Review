export type ReviewProject = {
  id: string;
  name: string;
  criteria_locked: boolean;
  created_at: string;
};

export type Criteria = {
  population: string | null;
  intervention: string | null;
  comparison: string | null;
  outcome: string | null;
  exclusion_rules: string[];
  notes: string | null;
};

export type ReviewProjectDetail = ReviewProject & {
  criteria: Criteria | null;
};

export type CriteriaInput = {
  population: string | null;
  intervention: string | null;
  comparison: string | null;
  outcome: string | null;
  exclusion_rules: string[];
  notes: string | null;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function listReviewProjects(): Promise<ReviewProject[]> {
  const response = await fetch(`${API_URL}/review-projects`);
  if (!response.ok) {
    throw new Error("Failed to load review projects");
  }
  return response.json();
}

export async function createReviewProject(name: string): Promise<ReviewProject> {
  const response = await fetch(`${API_URL}/review-projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) {
    throw new Error("Failed to create review project");
  }
  return response.json();
}

export async function getReviewProject(id: string): Promise<ReviewProjectDetail> {
  const response = await fetch(`${API_URL}/review-projects/${id}`);
  if (!response.ok) {
    throw new Error("Failed to load review project");
  }
  return response.json();
}

export async function saveCriteria(id: string, payload: CriteriaInput): Promise<Criteria> {
  const response = await fetch(`${API_URL}/review-projects/${id}/criteria`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Failed to save criteria");
  }
  return response.json();
}
