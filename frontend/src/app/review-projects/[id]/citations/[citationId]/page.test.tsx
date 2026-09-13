import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";

import CitationScreeningPage from "./page";

vi.mock("@/lib/api");

const mockedApi = vi.mocked(api);

const baseCitation = {
  id: "c1",
  title: "Metformin RCT",
  abstract: "A randomized trial of metformin.",
  authors: ["Doe J"],
  year: 2020,
  source: "PubMed",
  needs_abstract: false,
};

function renderPage() {
  return render(
    <CitationScreeningPage params={Promise.resolve({ id: "1", citationId: "c1" })} />
  );
}

describe("CitationScreeningPage", () => {
  beforeEach(() => {
    mockedApi.recordScreeningDecision.mockResolvedValue({
      decision: "include",
      reason: "Confirmed",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
  });

  it("shows the AI suggestion and pre-fills the decision form from it", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: { decision: "include", reason: "Matches all criteria." },
      suggestion_unavailable_reason: null,
      screening_decision: null,
    });

    renderPage();

    expect(await screen.findByText(/include:\s*matches all criteria/i)).toBeInTheDocument();
    expect(screen.getByLabelText("include")).toBeChecked();
    expect(screen.getByLabelText(/reason/i)).toHaveValue("Matches all criteria.");
  });

  it("shows why no suggestion is available when the abstract is missing", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      abstract: null,
      suggestion: null,
      suggestion_unavailable_reason: "missing_abstract",
      screening_decision: null,
    });

    renderPage();

    expect(await screen.findByText(/missing an abstract/i)).toBeInTheDocument();
  });

  it("shows a generation-failure message without blocking manual decisions", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: "generation_failed",
      screening_decision: null,
    });

    renderPage();

    expect(await screen.findByText(/generating an ai suggestion failed/i)).toBeInTheDocument();
  });

  it("pre-fills the form from an existing screening decision over the suggestion", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: { decision: "include", reason: "Matches all criteria." },
      suggestion_unavailable_reason: null,
      screening_decision: {
        decision: "exclude",
        reason: "Wrong population.",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    });

    renderPage();

    expect(await screen.findByLabelText("exclude")).toBeChecked();
    expect(screen.getByLabelText(/reason/i)).toHaveValue("Wrong population.");
  });

  it("records a screening decision on submit", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: { decision: "include", reason: "Matches all criteria." },
      suggestion_unavailable_reason: null,
      screening_decision: null,
    });

    renderPage();

    await screen.findByText(/include:\s*matches all criteria/i);
    fireEvent.click(screen.getByLabelText("exclude"));
    fireEvent.change(screen.getByLabelText(/reason/i), {
      target: { value: "Actually wrong population." },
    });
    fireEvent.click(screen.getByRole("button", { name: /save decision/i }));

    await waitFor(() =>
      expect(mockedApi.recordScreeningDecision).toHaveBeenCalledWith("1", "c1", {
        decision: "exclude",
        reason: "Actually wrong population.",
      })
    );
    expect(await screen.findByText(/decision saved/i)).toBeInTheDocument();
  });
});
