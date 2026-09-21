import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";

import { ConflictsPanel } from "./ConflictsPanel";

vi.mock("@/lib/api");

const mockedApi = vi.mocked(api);

const sampleConflict = {
  id: "conflict-1",
  citation: { id: "citation-1", title: "Effects of Aspirin on Recovery" },
  owner_decision: {
    decision: "include" as const,
    reason: "Meets criteria",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  co_reviewer_decision: {
    decision: "exclude" as const,
    reason: "Wrong population",
    created_at: "2026-01-02T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
  },
  created_at: "2026-01-02T00:00:00Z",
};

describe("ConflictsPanel", () => {
  beforeEach(() => {
    // Reset, not just re-default: one-shot values queued by a test that stopped
    // early would otherwise leak into the next.
    mockedApi.listConflicts.mockReset();
    mockedApi.resolveConflict.mockReset();
    mockedApi.listConflicts.mockResolvedValue([]);
  });

  it("shows a message when there are no outstanding conflicts", async () => {
    render(<ConflictsPanel reviewProjectId="1" isOwner={true} />);

    expect(await screen.findByText(/no outstanding conflicts/i)).toBeInTheDocument();
  });

  it("lists a conflict's two recorded decisions", async () => {
    mockedApi.listConflicts.mockResolvedValue([sampleConflict]);

    render(<ConflictsPanel reviewProjectId="1" isOwner={true} />);

    expect(await screen.findByText("Effects of Aspirin on Recovery")).toBeInTheDocument();
    expect(screen.getByText(/include: meets criteria/i)).toBeInTheDocument();
    expect(screen.getByText(/exclude: wrong population/i)).toBeInTheDocument();
  });

  it("lets the Owner resolve a conflict by picking the Owner's decision", async () => {
    mockedApi.listConflicts
      .mockResolvedValueOnce([sampleConflict])
      .mockResolvedValueOnce([]);
    mockedApi.resolveConflict.mockResolvedValue({
      id: "conflict-1",
      status: "resolved",
      resolved_decision: "include",
      resolved_reason: "Meets criteria",
      resolved_at: "2026-01-03T00:00:00Z",
    });

    render(<ConflictsPanel reviewProjectId="1" isOwner={true} />);

    fireEvent.click(await screen.findByRole("button", { name: /resolve/i }));

    await waitFor(() =>
      expect(mockedApi.resolveConflict).toHaveBeenCalledWith("1", "conflict-1", {
        decision: "include",
        reason: "Meets criteria",
      })
    );
    await waitFor(() =>
      expect(screen.getByText(/no outstanding conflicts/i)).toBeInTheDocument()
    );
  });

  it("lets the Owner resolve a conflict by picking the Co-Reviewer's decision", async () => {
    mockedApi.listConflicts
      .mockResolvedValueOnce([sampleConflict])
      .mockResolvedValueOnce([]);
    mockedApi.resolveConflict.mockResolvedValue({
      id: "conflict-1",
      status: "resolved",
      resolved_decision: "exclude",
      resolved_reason: "Wrong population",
      resolved_at: "2026-01-03T00:00:00Z",
    });

    render(<ConflictsPanel reviewProjectId="1" isOwner={true} />);
    await screen.findByText("Effects of Aspirin on Recovery");

    fireEvent.click(screen.getByRole("radio", { name: /use co-reviewer's decision/i }));
    fireEvent.click(screen.getByRole("button", { name: /resolve/i }));

    await waitFor(() =>
      expect(mockedApi.resolveConflict).toHaveBeenCalledWith("1", "conflict-1", {
        decision: "exclude",
        reason: "Wrong population",
      })
    );
  });

  it("lets the Owner resolve a conflict with a fresh decision", async () => {
    mockedApi.listConflicts
      .mockResolvedValueOnce([sampleConflict])
      .mockResolvedValueOnce([]);
    mockedApi.resolveConflict.mockResolvedValue({
      id: "conflict-1",
      status: "resolved",
      resolved_decision: "maybe",
      resolved_reason: "Discussed together",
      resolved_at: "2026-01-03T00:00:00Z",
    });

    render(<ConflictsPanel reviewProjectId="1" isOwner={true} />);
    await screen.findByText("Effects of Aspirin on Recovery");

    fireEvent.click(screen.getByRole("radio", { name: /enter a different decision/i }));
    fireEvent.change(screen.getByLabelText(/final decision/i), {
      target: { value: "maybe" },
    });
    fireEvent.change(screen.getByLabelText(/reason/i), {
      target: { value: "Discussed together" },
    });
    fireEvent.click(screen.getByRole("button", { name: /resolve/i }));

    await waitFor(() =>
      expect(mockedApi.resolveConflict).toHaveBeenCalledWith("1", "conflict-1", {
        decision: "maybe",
        reason: "Discussed together",
      })
    );
  });

  it("hides resolution controls from a non-Owner", async () => {
    mockedApi.listConflicts.mockResolvedValue([sampleConflict]);

    render(<ConflictsPanel reviewProjectId="1" isOwner={false} />);

    expect(await screen.findByText("Effects of Aspirin on Recovery")).toBeInTheDocument();
    expect(screen.getByText(/waiting for the owner/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /resolve/i })).not.toBeInTheDocument();
  });

  it("shows a loading state, not the empty confirmation, until the first load succeeds", async () => {
    let finishLoading!: (conflicts: (typeof sampleConflict)[]) => void;
    mockedApi.listConflicts.mockReturnValue(
      new Promise((resolve) => {
        finishLoading = resolve;
      })
    );

    render(<ConflictsPanel reviewProjectId="1" isOwner={true} />);

    expect(screen.getByText(/loading conflicts/i)).toBeInTheDocument();
    expect(screen.queryByText(/no outstanding conflicts/i)).not.toBeInTheDocument();

    finishLoading([]);

    expect(await screen.findByText(/no outstanding conflicts/i)).toBeInTheDocument();
    expect(screen.queryByText(/loading conflicts/i)).not.toBeInTheDocument();
  });

  it("shows the error and a retry, but not the empty confirmation, when the first load fails", async () => {
    mockedApi.listConflicts.mockRejectedValue(new Error("boom"));

    render(<ConflictsPanel reviewProjectId="1" isOwner={true} />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/failed to load conflicts/i);
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
    expect(screen.queryByText(/no outstanding conflicts/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/loading conflicts/i)).not.toBeInTheDocument();
  });

  it("clears the error and shows the empty confirmation when a retry finds no Conflicts", async () => {
    mockedApi.listConflicts.mockRejectedValueOnce(new Error("boom")).mockResolvedValueOnce([]);

    render(<ConflictsPanel reviewProjectId="1" isOwner={true} />);

    fireEvent.click(await screen.findByRole("button", { name: /try again/i }));

    expect(await screen.findByText(/no outstanding conflicts/i)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /try again/i })).not.toBeInTheDocument();
  });

  it("shows the Conflicts when a retry succeeds", async () => {
    mockedApi.listConflicts
      .mockRejectedValueOnce(new Error("boom"))
      .mockResolvedValueOnce([sampleConflict]);

    render(<ConflictsPanel reviewProjectId="1" isOwner={true} />);

    fireEvent.click(await screen.findByRole("button", { name: /try again/i }));

    expect(await screen.findByText("Effects of Aspirin on Recovery")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("keeps the rows already shown, with the error, when a later refresh fails", async () => {
    mockedApi.listConflicts
      .mockResolvedValueOnce([sampleConflict])
      .mockRejectedValueOnce(new Error("boom"));
    mockedApi.resolveConflict.mockResolvedValue({
      id: "conflict-1",
      status: "resolved",
      resolved_decision: "include",
      resolved_reason: "Meets criteria",
      resolved_at: "2026-01-03T00:00:00Z",
    });

    render(<ConflictsPanel reviewProjectId="1" isOwner={true} />);

    fireEvent.click(await screen.findByRole("button", { name: /resolve/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/failed to load conflicts/i);
    expect(screen.getByText("Effects of Aspirin on Recovery")).toBeInTheDocument();
    expect(screen.queryByText(/no outstanding conflicts/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("shows an error when resolving fails", async () => {
    mockedApi.listConflicts.mockResolvedValue([sampleConflict]);
    mockedApi.resolveConflict.mockRejectedValue(new Error("boom"));

    render(<ConflictsPanel reviewProjectId="1" isOwner={true} />);

    fireEvent.click(await screen.findByRole("button", { name: /resolve/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/failed to resolve/i);
  });
});
