import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";

import ReviewProjectDetailPage from "./page";

vi.mock("@/lib/api");

const mockedApi = vi.mocked(api);

const baseProject = {
  id: "1",
  name: "My Review",
  criteria_locked: false,
  created_at: "2026-01-01T00:00:00Z",
  citations_needing_decision: 0,
};

function renderPage() {
  return render(<ReviewProjectDetailPage params={Promise.resolve({ id: "1" })} />);
}

describe("ReviewProjectDetailPage", () => {
  beforeEach(() => {
    mockedApi.saveCriteria.mockResolvedValue({
      population: "Adults",
      intervention: null,
      comparison: null,
      outcome: null,
      exclusion_rules: [],
      notes: null,
    });
    mockedApi.listCitations.mockResolvedValue([]);
  });

  it("shows previously saved criteria", async () => {
    mockedApi.getReviewProject.mockResolvedValue({
      ...baseProject,
      criteria: {
        population: "Adults with diabetes",
        intervention: "Metformin",
        comparison: "Placebo",
        outcome: "HbA1c",
        exclusion_rules: ["Non-English"],
        notes: "Exclude conference abstracts.",
      },
    });

    renderPage();

    expect(await screen.findByDisplayValue("Adults with diabetes")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Metformin")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Placebo")).toBeInTheDocument();
    expect(screen.getByDisplayValue("HbA1c")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Non-English")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Exclude conference abstracts.")).toBeInTheDocument();
  });

  it("renders blank fields when no criteria exists yet", async () => {
    mockedApi.getReviewProject.mockResolvedValue({ ...baseProject, criteria: null });

    renderPage();

    await waitFor(() => expect(mockedApi.getReviewProject).toHaveBeenCalledWith("1"));
    expect(screen.getByLabelText(/population/i)).toHaveValue("");
  });

  it("saves criteria with blank PICO fields and exclusion rules", async () => {
    mockedApi.getReviewProject.mockResolvedValue({ ...baseProject, criteria: null });

    renderPage();

    await waitFor(() => expect(mockedApi.getReviewProject).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText(/exclusion rules/i), {
      target: { value: "Non-English\nCase reports" },
    });
    fireEvent.change(screen.getByLabelText(/notes/i), {
      target: { value: "Adult populations only." },
    });
    fireEvent.click(screen.getByRole("button", { name: /save criteria/i }));

    await waitFor(() =>
      expect(mockedApi.saveCriteria).toHaveBeenCalledWith("1", {
        population: null,
        intervention: null,
        comparison: null,
        outcome: null,
        exclusion_rules: ["Non-English", "Case reports"],
        notes: "Adult populations only.",
      })
    );
  });

  it("refreshes the live undecided count after uploading a citation", async () => {
    mockedApi.getReviewProject
      .mockResolvedValueOnce({ ...baseProject, criteria: null, citations_needing_decision: 0 })
      .mockResolvedValueOnce({ ...baseProject, criteria: null, citations_needing_decision: 1 });
    mockedApi.listCitations
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        {
          id: "c1",
          title: "New Citation",
          abstract: "Abstract",
          authors: [],
          year: 2022,
          source: null,
          needs_abstract: false,
        },
      ]);
    mockedApi.uploadCitations.mockResolvedValue({ created: 1, skipped: [] });

    renderPage();

    expect(await screen.findByText(/0 citation\(s\) still need a decision/i)).toBeInTheDocument();

    const file = new File(["title\nA\n"], "citations.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText(/upload ris or csv file/i), {
      target: { files: [file] },
    });

    expect(
      await screen.findByText(/1 citation\(s\) still need a decision/i)
    ).toBeInTheDocument();
  });
});
