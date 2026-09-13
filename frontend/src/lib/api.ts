export type ReviewProject = {
  id: string;
  name: string;
  criteria_locked: boolean;
  created_at: string;
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
