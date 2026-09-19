import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";
import { renderWithProject } from "@/test/renderWithProject";

import InvitationsPage from "./page";

vi.mock("@/lib/api");

const mockedApi = vi.mocked(api);

describe("InvitationsPage", () => {
  it("shows the Co-Reviewer section to the Owner of a Dual project", async () => {
    mockedApi.listInvitations.mockResolvedValue([]);
    renderWithProject(<InvitationsPage />, { project: { review_mode: "dual" }, isOwner: true });

    expect(await screen.findByRole("heading", { name: "Co-Reviewer" })).toBeInTheDocument();
    expect(mockedApi.listInvitations).toHaveBeenCalledWith("1");
  });

  it("says the section is unavailable to a Co-Reviewer, without loading anything", () => {
    renderWithProject(<InvitationsPage />, { project: { review_mode: "dual" }, isOwner: false });

    expect(screen.getByRole("alert")).toHaveTextContent(
      "This section isn't available for this project."
    );
    expect(mockedApi.listInvitations).not.toHaveBeenCalled();
  });

  it("says the section is unavailable for a Solo project, without loading anything", () => {
    renderWithProject(<InvitationsPage />, { project: { review_mode: "solo" }, isOwner: true });

    expect(screen.getByRole("alert")).toHaveTextContent(
      "This section isn't available for this project."
    );
    expect(mockedApi.listInvitations).not.toHaveBeenCalled();
  });

  it("refreshes the project after the Co-Reviewer is removed", async () => {
    mockedApi.listInvitations.mockResolvedValue([]);
    mockedApi.removeCoReviewer.mockResolvedValue({
      id: "1",
      name: "My Review",
      criteria_locked: false,
      merge_mode: "combine",
      review_mode: "dual",
      owner_reviewer_id: "owner-1",
      co_reviewer_id: null,
      created_at: "2026-01-01T00:00:00Z",
    });
    const { refreshProject } = renderWithProject(<InvitationsPage />, {
      project: { review_mode: "dual", co_reviewer_id: "co-1" },
      isOwner: true,
    });

    fireEvent.click(await screen.findByRole("button", { name: /remove co-reviewer/i }));

    await waitFor(() => expect(refreshProject).toHaveBeenCalledTimes(1));
  });
});
