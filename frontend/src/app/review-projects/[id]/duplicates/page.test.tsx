import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";
import { renderWithProject } from "@/test/renderWithProject";

import DuplicatesPage from "./page";

vi.mock("@/lib/api");

const mockedApi = vi.mocked(api);

describe("DuplicatesPage", () => {
  it("shows the Possible Duplicates section for the project", async () => {
    mockedApi.listPossibleDuplicates.mockResolvedValue([]);
    renderWithProject(<DuplicatesPage />);

    expect(await screen.findByRole("heading", { name: "Possible Duplicates" })).toBeInTheDocument();
    expect(mockedApi.listPossibleDuplicates).toHaveBeenCalledWith("1");
  });

  it("refreshes the project after a possible duplicate is dismissed", async () => {
    const citation = {
      id: "survivor-1",
      title: "Effects of Aspirin on Recovery",
      abstract: "An abstract",
      authors: ["Smith"],
      year: 2020,
      source: ["PubMed"],
      doi: "10.1/x",
      screening_decision: null,
      full_text_decision: null,
      full_text: null,
      extraction_values: [],
    };
    mockedApi.listPossibleDuplicates
      .mockResolvedValueOnce([
        {
          id: "pd-1",
          survivor: citation,
          loser: { ...citation, id: "loser-1" },
          conflicting_fields: [
            {
              field: "screening_decision",
              extraction_field_id: null,
              extraction_field_name: null,
            },
          ],
          created_at: "2026-01-02T00:00:00Z",
        },
      ])
      .mockResolvedValueOnce([]);
    mockedApi.dismissPossibleDuplicate.mockResolvedValue(undefined);
    const { refreshProject } = renderWithProject(<DuplicatesPage />);

    fireEvent.click(await screen.findByRole("button", { name: /dismiss/i }));

    await waitFor(() => expect(refreshProject).toHaveBeenCalledTimes(1));
  });
});
