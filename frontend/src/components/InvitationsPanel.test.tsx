import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";

import { InvitationsPanel } from "./InvitationsPanel";

vi.mock("@/lib/api");

const mockedApi = vi.mocked(api);

const pendingInvitation = {
  id: "inv-1",
  token: "secret-token",
  status: "pending" as const,
  created_at: "2026-01-01T00:00:00Z",
};

describe("InvitationsPanel", () => {
  beforeEach(() => {
    mockedApi.listInvitations.mockResolvedValue([]);
  });

  it("shows a message instead of invite management once a Co-Reviewer has joined", async () => {
    render(<InvitationsPanel reviewProjectId="1" hasCoReviewer />);

    expect(
      await screen.findByText(/a co-reviewer has joined this review project/i)
    ).toBeInTheDocument();
    expect(mockedApi.listInvitations).not.toHaveBeenCalled();
    expect(
      screen.queryByRole("button", { name: /generate invite link/i })
    ).not.toBeInTheDocument();
  });

  it("offers to generate an invite link when there is no outstanding invitation", async () => {
    render(<InvitationsPanel reviewProjectId="1" hasCoReviewer={false} />);

    expect(
      await screen.findByRole("button", { name: /generate invite link/i })
    ).toBeInTheDocument();
  });

  it("generates an invitation and shows its shareable link", async () => {
    mockedApi.createInvitation.mockResolvedValue(pendingInvitation);
    mockedApi.listInvitations
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([pendingInvitation]);

    render(<InvitationsPanel reviewProjectId="1" hasCoReviewer={false} />);

    fireEvent.click(await screen.findByRole("button", { name: /generate invite link/i }));

    await waitFor(() => expect(mockedApi.createInvitation).toHaveBeenCalledWith("1"));
    const link = await screen.findByDisplayValue(/\/invitations\/secret-token$/);
    expect(link).toBeInTheDocument();
  });

  it("revokes an outstanding invitation", async () => {
    mockedApi.listInvitations
      .mockResolvedValueOnce([pendingInvitation])
      .mockResolvedValueOnce([]);
    mockedApi.revokeInvitation.mockResolvedValue({
      ...pendingInvitation,
      status: "revoked",
    });

    render(<InvitationsPanel reviewProjectId="1" hasCoReviewer={false} />);

    fireEvent.click(await screen.findByRole("button", { name: /revoke/i }));

    await waitFor(() =>
      expect(mockedApi.revokeInvitation).toHaveBeenCalledWith("1", "inv-1")
    );
    expect(
      await screen.findByRole("button", { name: /generate invite link/i })
    ).toBeInTheDocument();
  });

  it("shows an error when generating an invitation fails", async () => {
    mockedApi.createInvitation.mockRejectedValue(
      new Error("Review Project already has a Co-Reviewer")
    );

    render(<InvitationsPanel reviewProjectId="1" hasCoReviewer={false} />);

    fireEvent.click(await screen.findByRole("button", { name: /generate invite link/i }));

    expect(
      await screen.findByText(/review project already has a co-reviewer/i)
    ).toBeInTheDocument();
  });
});
