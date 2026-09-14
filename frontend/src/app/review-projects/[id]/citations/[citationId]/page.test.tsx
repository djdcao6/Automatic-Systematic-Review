import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
  source: ["PubMed"],
  needs_abstract: false,
  screening_resolved: false,
  full_text_decision: null,
  full_text_suggestion: null,
  full_text_suggestion_unavailable_reason: null,
  extraction_fields: [],
  extraction_values: [],
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
    mockedApi.getReviewProject.mockResolvedValue({
      id: "1",
      name: "My Review",
      criteria_locked: false,
      created_at: "2026-01-01T00:00:00Z",
      criteria: {
        population: null,
        intervention: null,
        comparison: null,
        outcome: null,
        exclusion_rules: ["Wrong population", "Non-English language"],
        notes: null,
      },
      citations_needing_decision: 0,
    });
  });

  it("shows the AI suggestion and pre-fills the decision form from it", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: { decision: "include", reason: "Matches all criteria." },
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: null,
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
      full_text: null,
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
      full_text: null,
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
      full_text: null,
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
      full_text: null,
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

  it("shows an upload control when there is no Full Text yet", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: null,
    });

    renderPage();

    expect(await screen.findByText(/no full text uploaded yet/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/upload full text/i)).toBeInTheDocument();
  });

  it("uploads a Full Text and shows it once attached", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: null,
    });
    mockedApi.uploadFullText.mockResolvedValue({
      original_filename: "paper.pdf",
      parse_status: "parsed",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });

    renderPage();
    await screen.findByText(/no full text uploaded yet/i);

    const file = new File(["pdf-bytes"], "paper.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText(/upload full text/i), {
      target: { files: [file] },
    });

    await waitFor(() =>
      expect(mockedApi.uploadFullText).toHaveBeenCalledWith("1", "c1", file)
    );
    expect(await screen.findByText("paper.pdf")).toBeInTheDocument();
    expect(screen.getByLabelText(/replace full text/i)).toBeInTheDocument();
  });

  it("shows the parse-failed flag for a Full Text with no extractable text", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: {
        original_filename: "scanned.pdf",
        parse_status: "parse_failed",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    });

    renderPage();

    expect(await screen.findByText("scanned.pdf")).toBeInTheDocument();
    expect(
      await screen.findByText(/could not extract text from this pdf/i)
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/replace full text/i)).toBeInTheDocument();
  });

  it("replaces an existing Full Text via the same upload control", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: {
        original_filename: "v1.pdf",
        parse_status: "parsed",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    });
    mockedApi.uploadFullText.mockResolvedValue({
      original_filename: "v2.pdf",
      parse_status: "parsed",
      created_at: "2026-01-02T00:00:00Z",
      updated_at: "2026-01-02T00:00:00Z",
    });

    renderPage();
    await screen.findByText("v1.pdf");

    const file = new File(["pdf-bytes-2"], "v2.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText(/replace full text/i), {
      target: { files: [file] },
    });

    expect(await screen.findByText("v2.pdf")).toBeInTheDocument();
    expect(screen.queryByText("v1.pdf")).not.toBeInTheDocument();
  });

  it("shows an error when uploading a Full Text fails", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: null,
    });
    mockedApi.uploadFullText.mockRejectedValue(new Error("nope"));

    renderPage();
    await screen.findByText(/no full text uploaded yet/i);

    const file = new File(["pdf-bytes"], "paper.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText(/upload full text/i), {
      target: { files: [file] },
    });

    expect(await screen.findByText(/failed to upload full text/i)).toBeInTheDocument();
  });

  it("does not show a Full-Text Decision form when there is no Full Text yet", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: null,
    });

    renderPage();

    await screen.findByText(/no full text uploaded yet/i);
    expect(screen.queryByRole("group", { name: /full-text decision/i })).not.toBeInTheDocument();
  });

  it("records a Full-Text Decision once a Full Text is attached", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: { decision: "maybe", reason: null, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z" },
      full_text: {
        original_filename: "paper.pdf",
        parse_status: "parsed",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    });
    mockedApi.recordFullTextDecision.mockResolvedValue({
      decision: "include",
      reason: null,
      created_at: "2026-01-02T00:00:00Z",
      updated_at: "2026-01-02T00:00:00Z",
    });

    renderPage();
    const group = within(await screen.findByRole("group", { name: /full-text decision/i }));

    fireEvent.click(group.getByLabelText("include"));
    fireEvent.click(screen.getByRole("button", { name: /save full-text decision/i }));

    await waitFor(() =>
      expect(mockedApi.recordFullTextDecision).toHaveBeenCalledWith("1", "c1", {
        decision: "include",
        reason: null,
      })
    );
    expect(await screen.findByText(/full-text decision saved/i)).toBeInTheDocument();
  });

  it("offers a reason picker drawn from the Review Project's exclusion rules when excluding", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: {
        original_filename: "paper.pdf",
        parse_status: "parsed",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    });
    mockedApi.recordFullTextDecision.mockResolvedValue({
      decision: "exclude",
      reason: "Wrong population",
      created_at: "2026-01-02T00:00:00Z",
      updated_at: "2026-01-02T00:00:00Z",
    });

    renderPage();
    const group = within(await screen.findByRole("group", { name: /full-text decision/i }));
    fireEvent.click(group.getByLabelText("exclude"));

    const reasonSelect = await group.findByLabelText(/reason/i);
    expect(within(reasonSelect).getByText("Wrong population")).toBeInTheDocument();
    expect(within(reasonSelect).getByText("Non-English language")).toBeInTheDocument();

    fireEvent.change(reasonSelect, { target: { value: "Wrong population" } });
    fireEvent.click(screen.getByRole("button", { name: /save full-text decision/i }));

    await waitFor(() =>
      expect(mockedApi.recordFullTextDecision).toHaveBeenCalledWith("1", "c1", {
        decision: "exclude",
        reason: "Wrong population",
      })
    );
  });

  it("pre-fills the Full-Text Decision form from an existing decision", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: {
        original_filename: "paper.pdf",
        parse_status: "parsed",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      full_text_decision: {
        decision: "exclude",
        reason: "Wrong population",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    });

    renderPage();
    const group = within(await screen.findByRole("group", { name: /full-text decision/i }));

    expect(group.getByLabelText("exclude")).toBeChecked();
    expect(await group.findByLabelText(/reason/i)).toHaveValue("Wrong population");
  });

  it("does not show a Full-Text Suggestion section when there is no Full Text yet", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: null,
    });

    renderPage();

    await screen.findByText(/no full text uploaded yet/i);
    expect(screen.queryByText("Full-Text Suggestion")).not.toBeInTheDocument();
  });

  it("shows the Full-Text Suggestion decision, reason, and extraction field values", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: {
        original_filename: "paper.pdf",
        parse_status: "parsed",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      full_text_suggestion: {
        decision: "include",
        reason: "Meets all criteria.",
        extraction_values: [
          { extraction_field_id: "f1", name: "Sample size", value: "120 participants" },
        ],
      },
      full_text_suggestion_unavailable_reason: null,
    });

    renderPage();

    expect(
      await screen.findByText(/include:\s*meets all criteria/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/sample size:\s*120 participants/i)).toBeInTheDocument();
  });

  it("pre-fills the Full-Text Decision form from a Full-Text Suggestion when no decision exists yet", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: {
        original_filename: "paper.pdf",
        parse_status: "parsed",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      full_text_decision: null,
      full_text_suggestion: {
        decision: "include",
        reason: "Meets all criteria.",
        extraction_values: [],
      },
    });

    renderPage();
    const group = within(await screen.findByRole("group", { name: /full-text decision/i }));

    expect(group.getByLabelText("include")).toBeChecked();
  });

  it("shows why no Full-Text Suggestion is available when the PDF could not be parsed", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: {
        original_filename: "scanned.pdf",
        parse_status: "parse_failed",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      full_text_suggestion: null,
      full_text_suggestion_unavailable_reason: "parse_failed",
    });

    renderPage();

    expect(
      await screen.findByText(/could not be parsed, so no full-text suggestion/i)
    ).toBeInTheDocument();
  });

  it("shows an error when recording a Full-Text Decision fails", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: {
        original_filename: "paper.pdf",
        parse_status: "parsed",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    });
    mockedApi.recordFullTextDecision.mockRejectedValue(new Error("nope"));

    renderPage();
    const group = within(await screen.findByRole("group", { name: /full-text decision/i }));
    fireEvent.click(group.getByLabelText("include"));
    fireEvent.click(screen.getByRole("button", { name: /save full-text decision/i }));

    expect(await screen.findByText(/failed to save full-text decision/i)).toBeInTheDocument();
  });

  it("does not show an Extraction Values section when there are no extraction fields", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: null,
    });

    renderPage();

    await screen.findByText(/no full text uploaded yet/i);
    expect(screen.queryByText("Extraction Values")).not.toBeInTheDocument();
  });

  it("pre-fills the extraction values form from the Full-Text Suggestion", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: {
        original_filename: "paper.pdf",
        parse_status: "parsed",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      full_text_suggestion: {
        decision: "include",
        reason: "Meets all criteria.",
        extraction_values: [
          { extraction_field_id: "f1", name: "Sample size", value: "120 participants" },
        ],
      },
      extraction_fields: [
        {
          id: "f1",
          name: "Sample size",
          description: null,
          archived: false,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
    });

    renderPage();

    expect(await screen.findByLabelText("Sample size")).toHaveValue("120 participants");
  });

  it("pre-fills the extraction values form from a previously recorded value over the suggestion", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: null,
      full_text_suggestion: {
        decision: "include",
        reason: "Meets all criteria.",
        extraction_values: [
          { extraction_field_id: "f1", name: "Sample size", value: "120 participants" },
        ],
      },
      extraction_fields: [
        {
          id: "f1",
          name: "Sample size",
          description: null,
          archived: false,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
      extraction_values: [
        {
          extraction_field_id: "f1",
          name: "Sample size",
          value: "Confirmed at 118 participants",
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
    });

    renderPage();

    expect(await screen.findByLabelText("Sample size")).toHaveValue(
      "Confirmed at 118 participants"
    );
  });

  it("allows manual entry of an extraction value when no AI proposal is available", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: {
        original_filename: "scanned.pdf",
        parse_status: "parse_failed",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      full_text_suggestion: null,
      full_text_suggestion_unavailable_reason: "parse_failed",
      extraction_fields: [
        {
          id: "f1",
          name: "Sample size",
          description: null,
          archived: false,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
    });
    mockedApi.recordExtractionValue.mockResolvedValue({
      extraction_field_id: "f1",
      name: "Sample size",
      value: "Entered by hand",
      created_at: "2026-01-02T00:00:00Z",
      updated_at: "2026-01-02T00:00:00Z",
    });

    renderPage();

    const input = await screen.findByLabelText("Sample size");
    expect(input).toHaveValue("");
    fireEvent.change(input, { target: { value: "Entered by hand" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(mockedApi.recordExtractionValue).toHaveBeenCalledWith("1", "c1", "f1", {
        value: "Entered by hand",
      })
    );
    expect(await screen.findByText(/extraction value saved/i)).toBeInTheDocument();
  });

  it("confirms an AI-proposed extraction value as-is, recording it separately", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: {
        original_filename: "paper.pdf",
        parse_status: "parsed",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      full_text_suggestion: {
        decision: "include",
        reason: "Meets all criteria.",
        extraction_values: [
          { extraction_field_id: "f1", name: "Sample size", value: "120 participants" },
        ],
      },
      extraction_fields: [
        {
          id: "f1",
          name: "Sample size",
          description: null,
          archived: false,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
    });
    mockedApi.recordExtractionValue.mockResolvedValue({
      extraction_field_id: "f1",
      name: "Sample size",
      value: "120 participants",
      created_at: "2026-01-02T00:00:00Z",
      updated_at: "2026-01-02T00:00:00Z",
    });

    renderPage();

    await screen.findByLabelText("Sample size");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(mockedApi.recordExtractionValue).toHaveBeenCalledWith("1", "c1", "f1", {
        value: "120 participants",
      })
    );
  });

  it("overrides an AI-proposed extraction value by editing it before saving", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: {
        original_filename: "paper.pdf",
        parse_status: "parsed",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      full_text_suggestion: {
        decision: "include",
        reason: "Meets all criteria.",
        extraction_values: [
          { extraction_field_id: "f1", name: "Sample size", value: "120 participants" },
        ],
      },
      extraction_fields: [
        {
          id: "f1",
          name: "Sample size",
          description: null,
          archived: false,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
    });
    mockedApi.recordExtractionValue.mockResolvedValue({
      extraction_field_id: "f1",
      name: "Sample size",
      value: "118 participants (corrected)",
      created_at: "2026-01-02T00:00:00Z",
      updated_at: "2026-01-02T00:00:00Z",
    });

    renderPage();

    const input = await screen.findByLabelText("Sample size");
    expect(input).toHaveValue("120 participants");
    fireEvent.change(input, { target: { value: "118 participants (corrected)" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(mockedApi.recordExtractionValue).toHaveBeenCalledWith("1", "c1", "f1", {
        value: "118 participants (corrected)",
      })
    );
    expect(await screen.findByText(/extraction value saved/i)).toBeInTheDocument();
  });

  it("shows an error when recording an extraction value fails", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: null,
      extraction_fields: [
        {
          id: "f1",
          name: "Sample size",
          description: null,
          archived: false,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
    });
    mockedApi.recordExtractionValue.mockRejectedValue(new Error("nope"));

    renderPage();

    const input = await screen.findByLabelText("Sample size");
    fireEvent.change(input, { target: { value: "80 participants" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText(/failed to save extraction value/i)).toBeInTheDocument();
  });
});
