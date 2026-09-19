import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";
import * as pngExport from "@/lib/png-export";

import FlowDiagramPage from "./page";

vi.mock("@/lib/api");
vi.mock("@/lib/png-export");

const mockedApi = vi.mocked(api);
const mockedPngExport = vi.mocked(pngExport);

const baseProject = {
  id: "1",
  name: "My Review",
  criteria_locked: false,
  merge_mode: "combine" as const,
  review_mode: "solo" as const,
  owner_reviewer_id: "owner-1",
  co_reviewer_id: null,
  created_at: "2026-01-01T00:00:00Z",
  citations_needing_decision: 0,
  criteria: null,
};

function renderPage() {
  return render(<FlowDiagramPage params={Promise.resolve({ id: "1" })} />);
}

describe("FlowDiagramPage", () => {
  beforeEach(() => {
    mockedApi.getReviewProject.mockResolvedValue(baseProject);
  });

  it("renders per-source identification counts, duplicates removed, and screening totals", async () => {
    mockedApi.getFlowDiagram.mockResolvedValue({
      criteria: null,
      identification_counts: { PubMed: 3, Embase: 2 },
      duplicates_removed: 1,
      screened: 2,
      excluded: 1,
      pending: 2,
      full_text_assessed: 0,
      full_text_excluded_by_reason: {},
      full_text_included: 0,
      full_text_pending: 0,
    });

    renderPage();

    expect(await screen.findByText("PubMed: 3")).toBeInTheDocument();
    expect(screen.getByText("Embase: 2")).toBeInTheDocument();
    expect(screen.getByText(/total records identified: 5/i)).toBeInTheDocument();
    expect(screen.getByText(/duplicates removed: 1/i)).toBeInTheDocument();
    expect(screen.getByText(/records screened: 2/i)).toBeInTheDocument();
    expect(screen.getByText(/records excluded: 1/i)).toBeInTheDocument();
  });

  it("notes the pending-decision count", async () => {
    mockedApi.getFlowDiagram.mockResolvedValue({
      criteria: null,
      identification_counts: { PubMed: 3 },
      duplicates_removed: 0,
      screened: 1,
      excluded: 0,
      pending: 2,
      full_text_assessed: 0,
      full_text_excluded_by_reason: {},
      full_text_included: 0,
      full_text_pending: 0,
    });

    renderPage();

    expect(
      await screen.findByText(/2 citation\(s\) still pending a screening decision/i)
    ).toBeInTheDocument();
  });

  it("renders a plain numeric summary table with the same figures as the diagram", async () => {
    mockedApi.getFlowDiagram.mockResolvedValue({
      criteria: null,
      identification_counts: { PubMed: 3, Embase: 2 },
      duplicates_removed: 1,
      screened: 2,
      excluded: 1,
      pending: 2,
      full_text_assessed: 0,
      full_text_excluded_by_reason: {},
      full_text_included: 0,
      full_text_pending: 0,
    });

    renderPage();

    const table = await screen.findByRole("table");
    expect(table).toHaveTextContent("Identified (PubMed)");
    expect(table).toHaveTextContent("Identified (Embase)");
    expect(table).toHaveTextContent("Total Identified");
    expect(table).toHaveTextContent("Duplicates Removed");
    expect(table).toHaveTextContent("Screened");
    expect(table).toHaveTextContent("Excluded");
    expect(table).toHaveTextContent("Pending Decision");
  });

  it("renders the Review Project's Criteria as a header", async () => {
    mockedApi.getFlowDiagram.mockResolvedValue({
      criteria: {
        population: "Adults with diabetes",
        intervention: "Metformin",
        comparison: "Placebo",
        outcome: "HbA1c",
        exclusion_rules: ["Non-English", "Case reports"],
        notes: "Focus on RCTs only",
      },
      identification_counts: {},
      duplicates_removed: 0,
      screened: 0,
      excluded: 0,
      pending: 0,
      full_text_assessed: 0,
      full_text_excluded_by_reason: {},
      full_text_included: 0,
      full_text_pending: 0,
    });

    renderPage();

    expect(await screen.findByText("Adults with diabetes")).toBeInTheDocument();
    expect(screen.getByText("Metformin")).toBeInTheDocument();
    expect(screen.getByText("Placebo")).toBeInTheDocument();
    expect(screen.getByText("HbA1c")).toBeInTheDocument();
    expect(screen.getByText("Non-English")).toBeInTheDocument();
    expect(screen.getByText("Case reports")).toBeInTheDocument();
  });

  it("shows a message when no Criteria has been saved yet", async () => {
    mockedApi.getFlowDiagram.mockResolvedValue({
      criteria: null,
      identification_counts: {},
      duplicates_removed: 0,
      screened: 0,
      excluded: 0,
      pending: 0,
      full_text_assessed: 0,
      full_text_excluded_by_reason: {},
      full_text_included: 0,
      full_text_pending: 0,
    });

    renderPage();

    expect(
      await screen.findByText(/no criteria saved yet for this review project/i)
    ).toBeInTheDocument();
  });

  it("shows an error when the flow diagram fails to load", async () => {
    mockedApi.getFlowDiagram.mockRejectedValue(new Error("boom"));

    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent(/failed to load prisma flow diagram/i);
  });

  it("renders full-text assessed, itemized excluded-by-reason, and included counts", async () => {
    mockedApi.getFlowDiagram.mockResolvedValue({
      criteria: null,
      identification_counts: { PubMed: 5 },
      duplicates_removed: 0,
      screened: 5,
      excluded: 0,
      pending: 0,
      full_text_assessed: 4,
      full_text_excluded_by_reason: { "Wrong population": 2, "Not RCT": 1 },
      full_text_included: 1,
      full_text_pending: 1,
    });

    renderPage();

    expect(await screen.findByText(/full-text assessed: 4/i)).toBeInTheDocument();
    expect(screen.getByText(/wrong population: 2/i)).toBeInTheDocument();
    expect(screen.getByText(/not rct: 1/i)).toBeInTheDocument();
    expect(screen.getByText(/included: 1/i)).toBeInTheDocument();
  });

  it("notes the full-text pending-decision count", async () => {
    mockedApi.getFlowDiagram.mockResolvedValue({
      criteria: null,
      identification_counts: { PubMed: 5 },
      duplicates_removed: 0,
      screened: 5,
      excluded: 0,
      pending: 0,
      full_text_assessed: 3,
      full_text_excluded_by_reason: {},
      full_text_included: 3,
      full_text_pending: 2,
    });

    renderPage();

    expect(
      await screen.findByText(/2 citation\(s\) still pending a full-text decision/i)
    ).toBeInTheDocument();
  });

  it("renders full-text figures in the plain numeric summary table", async () => {
    mockedApi.getFlowDiagram.mockResolvedValue({
      criteria: null,
      identification_counts: { PubMed: 5 },
      duplicates_removed: 0,
      screened: 5,
      excluded: 0,
      pending: 0,
      full_text_assessed: 4,
      full_text_excluded_by_reason: { "Wrong population": 2, "Not RCT": 1 },
      full_text_included: 1,
      full_text_pending: 1,
    });

    renderPage();

    const table = await screen.findByRole("table");
    expect(table).toHaveTextContent("Full-Text Assessed");
    expect(table).toHaveTextContent("Full-Text Excluded (Wrong population)");
    expect(table).toHaveTextContent("Full-Text Excluded (Not RCT)");
    expect(table).toHaveTextContent("Full-Text Included");
    expect(table).toHaveTextContent("Full-Text Pending Decision");
  });

  it("rasterizes the rendered diagram to a PNG and downloads it when 'Download as PNG' is clicked", async () => {
    mockedApi.getFlowDiagram.mockResolvedValue({
      criteria: null,
      identification_counts: { PubMed: 3 },
      duplicates_removed: 1,
      screened: 2,
      excluded: 1,
      pending: 2,
      full_text_assessed: 0,
      full_text_excluded_by_reason: {},
      full_text_included: 0,
      full_text_pending: 0,
    });
    mockedPngExport.downloadElementAsPng.mockResolvedValue();

    renderPage();

    const button = await screen.findByRole("button", { name: /download as png/i });
    fireEvent.click(button);

    expect(mockedPngExport.downloadElementAsPng).toHaveBeenCalledTimes(1);
    const [element, filename] = mockedPngExport.downloadElementAsPng.mock.calls[0];
    expect(element).toBeInstanceOf(HTMLElement);
    expect(element).toHaveAccessibleName("PRISMA Flow Diagram");
    expect(filename).toBe("prisma-flow-diagram.png");
  });

  it("shows an error when the PNG download fails", async () => {
    mockedApi.getFlowDiagram.mockResolvedValue({
      criteria: null,
      identification_counts: { PubMed: 3 },
      duplicates_removed: 0,
      screened: 0,
      excluded: 0,
      pending: 0,
      full_text_assessed: 0,
      full_text_excluded_by_reason: {},
      full_text_included: 0,
      full_text_pending: 0,
    });
    mockedPngExport.downloadElementAsPng.mockRejectedValue(new Error("boom"));

    renderPage();

    const button = await screen.findByRole("button", { name: /download as png/i });
    fireEvent.click(button);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /failed to download prisma flow diagram as png/i
    );
  });
  describe("before the diagram has loaded", () => {
    it("keeps the loading message inside the page's main", async () => {
      mockedApi.getFlowDiagram.mockReturnValueOnce(new Promise(() => {}));

      renderPage();
      await vi.waitFor(() => expect(mockedApi.getFlowDiagram).toHaveBeenCalled());

      expect(screen.getByRole("main")).toHaveTextContent("Loading...");
    });

    it("keeps the load failure inside main", async () => {
      mockedApi.getFlowDiagram.mockRejectedValueOnce(new Error("down"));

      renderPage();

      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent(/failed to load prisma flow diagram/i);
      expect(screen.getByRole("main")).toContainElement(alert);
    });
  });
});
