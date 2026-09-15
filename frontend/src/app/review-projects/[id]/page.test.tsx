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
  merge_mode: "combine" as const,
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
    mockedApi.listExtractionFields.mockResolvedValue([]);
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
          source: [],
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

  it("exports the review project as a CSV file using the server-provided filename", async () => {
    mockedApi.getReviewProject.mockResolvedValue({ ...baseProject, criteria: null });
    mockedApi.exportReviewProject.mockResolvedValue({
      blob: new Blob(["title\n"], { type: "text/csv" }),
      filename: "my-review-a1b2c3d4.csv",
    });
    const createObjectURL = vi.fn().mockReturnValue("blob:mock-url");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL });
    const appendChildSpy = vi.spyOn(document.body, "appendChild");

    renderPage();

    await waitFor(() => expect(mockedApi.getReviewProject).toHaveBeenCalledWith("1"));

    fireEvent.click(screen.getByRole("button", { name: /export csv/i }));

    await waitFor(() => expect(mockedApi.exportReviewProject).toHaveBeenCalledWith("1"));
    expect(createObjectURL).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock-url");
    const link = appendChildSpy.mock.calls
      .map((call) => call[0])
      .find((node): node is HTMLAnchorElement => node instanceof HTMLAnchorElement);
    expect(link?.download).toBe("my-review-a1b2c3d4.csv");

    appendChildSpy.mockRestore();
    vi.unstubAllGlobals();
  });

  it("shows an error when the export request fails", async () => {
    mockedApi.getReviewProject.mockResolvedValue({ ...baseProject, criteria: null });
    mockedApi.exportReviewProject.mockRejectedValue(new Error("boom"));

    renderPage();

    await waitFor(() => expect(mockedApi.getReviewProject).toHaveBeenCalledWith("1"));

    fireEvent.click(screen.getByRole("button", { name: /export csv/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/failed to export/i);
  });
});
