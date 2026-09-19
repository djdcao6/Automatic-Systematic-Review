import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";
import { renderWithProject } from "@/test/renderWithProject";

import ConflictsPage from "./page";

vi.mock("@/lib/api");

const mockedApi = vi.mocked(api);

describe("ConflictsPage", () => {
  it("shows the Conflicts section of a Dual project to a Co-Reviewer too", async () => {
    mockedApi.listConflicts.mockResolvedValue([]);
    renderWithProject(<ConflictsPage />, { project: { review_mode: "dual" }, isOwner: false });

    expect(await screen.findByRole("heading", { name: "Conflicts" })).toBeInTheDocument();
    expect(mockedApi.listConflicts).toHaveBeenCalledWith("1");
  });

  it("says the section is unavailable for a Solo project, without loading anything", () => {
    renderWithProject(<ConflictsPage />, { project: { review_mode: "solo" } });

    expect(screen.getByRole("alert")).toHaveTextContent(
      "This section isn't available for this project."
    );
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(mockedApi.listConflicts).not.toHaveBeenCalled();
  });

  it("refreshes the project after the Owner resolves a conflict", async () => {
    mockedApi.listConflicts
      .mockResolvedValueOnce([
        {
          id: "conflict-1",
          citation: { id: "citation-1", title: "Effects of Aspirin on Recovery" },
          owner_decision: {
            decision: "include",
            reason: "Meets criteria",
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
          },
          co_reviewer_decision: {
            decision: "exclude",
            reason: "Wrong population",
            created_at: "2026-01-02T00:00:00Z",
            updated_at: "2026-01-02T00:00:00Z",
          },
          created_at: "2026-01-02T00:00:00Z",
        },
      ])
      .mockResolvedValueOnce([]);
    mockedApi.resolveConflict.mockResolvedValue({
      id: "conflict-1",
      status: "resolved",
      resolved_decision: "include",
      resolved_reason: "Meets criteria",
      resolved_at: "2026-01-03T00:00:00Z",
    });
    const { refreshProject } = renderWithProject(<ConflictsPage />, {
      project: { review_mode: "dual" },
      isOwner: true,
    });

    fireEvent.click(await screen.findByRole("button", { name: /resolve/i }));

    await waitFor(() => expect(refreshProject).toHaveBeenCalledTimes(1));
  });
});
