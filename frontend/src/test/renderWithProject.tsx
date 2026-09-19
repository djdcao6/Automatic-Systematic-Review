import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { vi } from "vitest";

import type { ReviewProjectDetail } from "@/lib/api";
import { ReviewProjectProvider } from "@/lib/ReviewProjectContext";

export const baseProject: ReviewProjectDetail = {
  id: "1",
  name: "My Review",
  criteria_locked: false,
  merge_mode: "combine",
  review_mode: "solo",
  owner_reviewer_id: "owner-1",
  co_reviewer_id: null,
  created_at: "2026-01-01T00:00:00Z",
  citations_needing_decision: 0,
  criteria: null,
};

// Renders a section page the way ProjectShell would: with the project, whether
// the viewer owns it, and a refreshProject the page can call.
export function renderWithProject(
  ui: ReactElement,
  {
    project = {},
    isOwner = true,
    refreshProject = vi.fn().mockResolvedValue(undefined),
  }: {
    project?: Partial<ReviewProjectDetail>;
    isOwner?: boolean;
    refreshProject?: () => Promise<void>;
  } = {}
) {
  return {
    refreshProject,
    ...render(
      <ReviewProjectProvider value={{ project: { ...baseProject, ...project }, isOwner, refreshProject }}>
        {ui}
      </ReviewProjectProvider>
    ),
  };
}
