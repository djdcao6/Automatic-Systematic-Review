import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";

import { PossibleDuplicatesPanel } from "./PossibleDuplicatesPanel";

vi.mock("@/lib/api");

const mockedApi = vi.mocked(api);

const survivor = {
  id: "survivor-1",
  title: "Effects of Aspirin on Recovery",
  abstract: "An abstract",
  authors: ["Smith"],
  year: 2020,
  source: ["PubMed"],
  doi: "10.1/x",
  screening_decision: {
    decision: "include" as const,
    reason: "Meets criteria",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  full_text_decision: null,
  full_text: null,
  extraction_values: [],
};

const loser = {
  ...survivor,
  id: "loser-1",
  screening_decision: {
    decision: "exclude" as const,
    reason: "Wrong population",
    created_at: "2026-01-02T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
  },
};

const samplePossibleDuplicate = {
  id: "pd-1",
  survivor,
  loser,
  conflicting_fields: [
    { field: "screening_decision" as const, extraction_field_id: null, extraction_field_name: null },
  ],
  created_at: "2026-01-02T00:00:00Z",
};

describe("PossibleDuplicatesPanel", () => {
  beforeEach(() => {
    mockedApi.listPossibleDuplicates.mockResolvedValue([]);
  });

  it("shows a message when there are no outstanding possible duplicates", async () => {
    render(<PossibleDuplicatesPanel reviewProjectId="1" />);

    expect(await screen.findByText(/no outstanding possible duplicates/i)).toBeInTheDocument();
  });

  it("lists a possible duplicate's conflicting fields side by side", async () => {
    mockedApi.listPossibleDuplicates.mockResolvedValue([samplePossibleDuplicate]);

    render(<PossibleDuplicatesPanel reviewProjectId="1" />);

    expect(await screen.findByText("Effects of Aspirin on Recovery")).toBeInTheDocument();
    expect(screen.getByText("Screening Decision")).toBeInTheDocument();
    expect(screen.getByText("include")).toBeInTheDocument();
    expect(screen.getByText("exclude")).toBeInTheDocument();
  });

  it("resolves a possible duplicate with the reviewer's chosen side", async () => {
    mockedApi.listPossibleDuplicates
      .mockResolvedValueOnce([samplePossibleDuplicate])
      .mockResolvedValueOnce([]);
    mockedApi.resolvePossibleDuplicate.mockResolvedValue({
      id: "survivor-1",
      title: survivor.title,
      abstract: survivor.abstract,
      authors: survivor.authors,
      year: survivor.year,
      source: survivor.source,
      needs_abstract: false,
      blocked_pending_co_reviewer: false,
    });

    render(<PossibleDuplicatesPanel reviewProjectId="1" />);

    const row = (await screen.findByText("Screening Decision")).closest("tr");
    expect(row).not.toBeNull();
    fireEvent.click(within(row as HTMLElement).getByText("exclude"));
    fireEvent.click(screen.getByRole("button", { name: /resolve/i }));

    await waitFor(() =>
      expect(mockedApi.resolvePossibleDuplicate).toHaveBeenCalledWith("1", "pd-1", [
        { field: "screening_decision", extraction_field_id: null, winner: "loser" },
      ])
    );
    await waitFor(() =>
      expect(screen.getByText(/no outstanding possible duplicates/i)).toBeInTheDocument()
    );
  });

  it("dismisses a possible duplicate and removes it from the list", async () => {
    mockedApi.listPossibleDuplicates
      .mockResolvedValueOnce([samplePossibleDuplicate])
      .mockResolvedValueOnce([]);
    mockedApi.dismissPossibleDuplicate.mockResolvedValue(undefined);

    render(<PossibleDuplicatesPanel reviewProjectId="1" />);

    fireEvent.click(await screen.findByRole("button", { name: /dismiss/i }));

    await waitFor(() =>
      expect(mockedApi.dismissPossibleDuplicate).toHaveBeenCalledWith("1", "pd-1")
    );
    await waitFor(() =>
      expect(screen.getByText(/no outstanding possible duplicates/i)).toBeInTheDocument()
    );
  });

  it("shows an error when resolving fails", async () => {
    mockedApi.listPossibleDuplicates.mockResolvedValue([samplePossibleDuplicate]);
    mockedApi.resolvePossibleDuplicate.mockRejectedValue(new Error("boom"));

    render(<PossibleDuplicatesPanel reviewProjectId="1" />);

    fireEvent.click(await screen.findByRole("button", { name: /resolve/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/failed to resolve/i);
  });

  it("shows an error when dismissing fails", async () => {
    mockedApi.listPossibleDuplicates.mockResolvedValue([samplePossibleDuplicate]);
    mockedApi.dismissPossibleDuplicate.mockRejectedValue(new Error("boom"));

    render(<PossibleDuplicatesPanel reviewProjectId="1" />);

    fireEvent.click(await screen.findByRole("button", { name: /dismiss/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/failed to dismiss/i);
  });
});
