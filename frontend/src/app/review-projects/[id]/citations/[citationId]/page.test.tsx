import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { StrictMode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectShell } from "@/components/ProjectShell";
import * as api from "@/lib/api";

import CitationScreeningPage from "./page";

vi.mock("@/lib/api");
vi.mock("next/navigation", () => ({
  useSelectedLayoutSegment: () => "citations",
}));

const mockedApi = vi.mocked(api);

const baseCitation = {
  id: "c1",
  title: "Metformin RCT",
  abstract: "A randomized trial of metformin.",
  authors: ["Doe J"],
  year: 2020,
  source: ["PubMed"],
  needs_abstract: false,
  blocked_pending_co_reviewer: false,
  position: null,
  total: 0,
  previous_citation_id: null,
  next_citation_id: null,
  peer_screening_decision: null,
  suggestion_needs_generation: false,
  screening_blind: false,
  screening_resolved: false,
  full_text_decision: null,
  full_text_suggestion: null,
  full_text_suggestion_unavailable_reason: null,
  full_text_suggestion_needs_generation: false,
  extraction_fields: [],
  extraction_values: [],
};

const dualReviewProject = {
  id: "1",
  name: "My Dual Review",
  criteria_locked: false,
  merge_mode: "combine" as const,
  review_mode: "dual" as const,
  owner_reviewer_id: "owner-1",
  co_reviewer_id: "co-reviewer-1",
  created_at: "2026-01-01T00:00:00Z",
  criteria: {
    population: null,
    intervention: null,
    comparison: null,
    outcome: null,
    exclusion_rules: [],
    notes: null,
  },
  citations_needing_decision: 0,
};

const parsedFullText = {
  original_filename: "paper.pdf",
  parse_status: "parsed" as const,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const sampleSizeField = {
  id: "f1",
  name: "Sample size",
  description: null,
  archived: false,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const suggestionWithSampleSize = {
  decision: "include" as const,
  reason: "Meets all criteria.",
  extraction_values: [
    { extraction_field_id: "f1", name: "Sample size", value: "120 participants" },
  ],
};

// A promise the test settles by hand, to check the page while a request is in flight.
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function chooseFile(label: RegExp, name = "paper.pdf") {
  const file = new File(["pdf-bytes"], name, { type: "application/pdf" });
  fireEvent.change(screen.getByLabelText(label), { target: { files: [file] } });
  return file;
}

// The page sits inside the project's shell, which supplies the project.
function renderPage() {
  return render(
    <ProjectShell reviewProjectId="1">
      <CitationScreeningPage params={Promise.resolve({ id: "1", citationId: "c1" })} />
    </ProjectShell>
  );
}

describe("CitationScreeningPage", () => {
  beforeEach(() => {
    mockedApi.generateSuggestion.mockReset();
    mockedApi.generateFullTextSuggestion.mockReset();
    mockedApi.recordFullTextDecision.mockReset();
    mockedApi.recordExtractionValue.mockReset();
    mockedApi.getMe.mockResolvedValue({
      id: "owner-1",
      email: "owner@example.com",
      created_at: "2026-01-01T00:00:00Z",
    });
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
      merge_mode: "combine",
      review_mode: "solo",
      owner_reviewer_id: "owner-1",
      co_reviewer_id: null,
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

  it("shows the AI suggestion in the margin but leaves the decision and reason to the reviewer", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: { decision: "include", reason: "Matches all criteria." },
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: null,
    });

    renderPage();

    expect(await screen.findByText(/include:\s*matches all criteria/i)).toBeInTheDocument();
    expect(screen.getByLabelText("include")).not.toBeChecked();
    expect(screen.getByLabelText("exclude")).not.toBeChecked();
    expect(screen.getByLabelText("maybe")).not.toBeChecked();
    expect(screen.getByLabelText(/reason/i)).toHaveValue("");
    // Already generated on an earlier visit, so nothing is requested again.
    expect(mockedApi.generateSuggestion).not.toHaveBeenCalled();
  });

  it("shows the citation at once, then the generated suggestion in the margin", async () => {
    const generation = deferred<api.SuggestionOutcome>();
    mockedApi.generateSuggestion.mockReturnValue(generation.promise);
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      suggestion_needs_generation: true,
      screening_decision: null,
      full_text: null,
    });

    renderPage();

    expect(await screen.findByText("A randomized trial of metformin.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /save decision/i })).toBeInTheDocument();
    expect(screen.getByText(/preparing an ai suggestion/i)).toHaveAttribute("role", "status");

    generation.resolve({
      suggestion: { decision: "include", reason: "Matches all criteria." },
      suggestion_unavailable_reason: null,
    });

    expect(await screen.findByText(/include:\s*matches all criteria/i)).toBeInTheDocument();
    expect(screen.queryByText(/preparing an ai suggestion/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText("include")).not.toBeChecked();
    expect(screen.getByLabelText(/reason/i)).toHaveValue("");
    expect(mockedApi.generateSuggestion).toHaveBeenCalledTimes(1);
    expect(mockedApi.generateSuggestion).toHaveBeenCalledWith("1", "c1");
  });

  it.each([
    [
      "the server reports a failed generation",
      () =>
        mockedApi.generateSuggestion.mockResolvedValue({
          suggestion: null,
          suggestion_unavailable_reason: "generation_failed",
        }),
    ],
    [
      "the request itself fails",
      () => mockedApi.generateSuggestion.mockRejectedValue(new Error("network down")),
    ],
  ])("shows the failure message when %s, and leaves manual decisions open", async (_, arrange) => {
    arrange();
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      suggestion_needs_generation: true,
      screening_decision: null,
      full_text: null,
    });

    renderPage();

    expect(await screen.findByText(/generating an ai suggestion failed/i)).toBeInTheDocument();
    expect(screen.queryByText(/preparing an ai suggestion/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /save decision/i })).toBeEnabled();
  });

  it("asks for the suggestion while blind but shows nothing of it", async () => {
    mockedApi.getReviewProject.mockResolvedValue(dualReviewProject);
    mockedApi.generateSuggestion.mockResolvedValue({
      suggestion: null,
      suggestion_unavailable_reason: null,
    });
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      suggestion_needs_generation: true,
      screening_decision: null,
      screening_blind: true,
      full_text: null,
    });

    renderPage();

    expect(
      await screen.findByText(/hidden until you record your own screening decision/i)
    ).toBeInTheDocument();
    await waitFor(() => expect(mockedApi.generateSuggestion).toHaveBeenCalledTimes(1));
    expect(screen.queryByText(/preparing an ai suggestion/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/generating an ai suggestion failed/i)).not.toBeInTheDocument();
  });

  describe("saving a decision while the suggestion is still being generated (blind Dual)", () => {
    const stamp = "2026-01-01T00:00:00Z";
    const blindCitation = {
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      suggestion_needs_generation: true,
      screening_decision: null,
      screening_blind: true,
      full_text: null,
    };
    const ownDecision = { decision: "include" as const, reason: null, created_at: stamp, updated_at: stamp };
    // The server sends a blind Reviewer nothing about the suggestion, even once it is ready.
    const emptyAnswer = { suggestion: null, suggestion_unavailable_reason: null };

    async function saveWhileBlind() {
      renderPage();
      await screen.findByText(/hidden until you record your own screening decision/i);
      fireEvent.click(screen.getByLabelText("include"));
      fireEvent.click(screen.getByRole("button", { name: /save decision/i }));
      await screen.findByText(/decision saved/i);
    }

    it("shows the suggestion once it is ready, without a reload", async () => {
      const generation = deferred<api.SuggestionOutcome>();
      mockedApi.getReviewProject.mockResolvedValue(dualReviewProject);
      mockedApi.generateSuggestion.mockReturnValue(generation.promise);
      mockedApi.getCitation
        .mockResolvedValueOnce(blindCitation)
        .mockResolvedValueOnce({
          ...blindCitation,
          screening_blind: false,
          screening_decision: ownDecision,
        })
        .mockResolvedValue({
          ...blindCitation,
          screening_blind: false,
          screening_decision: ownDecision,
          suggestion: { decision: "exclude", reason: "Wrong population." },
          suggestion_needs_generation: false,
        });

      await saveWhileBlind();
      expect(screen.getByText(/preparing an ai suggestion/i)).toBeInTheDocument();

      generation.resolve(emptyAnswer);

      expect(await screen.findByText(/exclude:\s*wrong population/i)).toBeInTheDocument();
      expect(screen.queryByText(/preparing an ai suggestion/i)).not.toBeInTheDocument();
      expect(mockedApi.generateSuggestion).toHaveBeenCalledTimes(1);
    });

    it("asks once more if generating it failed, and reports a second failure", async () => {
      const firstAttempt = deferred<api.SuggestionOutcome>();
      mockedApi.getReviewProject.mockResolvedValue(dualReviewProject);
      mockedApi.generateSuggestion.mockReturnValueOnce(firstAttempt.promise).mockResolvedValueOnce({
        suggestion: null,
        suggestion_unavailable_reason: "generation_failed",
      });
      mockedApi.getCitation.mockResolvedValueOnce(blindCitation).mockResolvedValue({
        ...blindCitation,
        screening_blind: false,
        screening_decision: ownDecision,
      });

      await saveWhileBlind();
      firstAttempt.resolve(emptyAnswer);

      expect(await screen.findByText(/generating an ai suggestion failed/i)).toBeInTheDocument();
      expect(mockedApi.generateSuggestion).toHaveBeenCalledTimes(2);
    });
  });

  it("sends one request under React Strict Mode and still shows the suggestion", async () => {
    mockedApi.generateSuggestion.mockResolvedValue({
      suggestion: { decision: "include", reason: "Matches all criteria." },
      suggestion_unavailable_reason: null,
    });
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      suggestion_needs_generation: true,
      screening_decision: null,
      full_text: null,
    });

    render(
      <StrictMode>
        <ProjectShell reviewProjectId="1">
          <CitationScreeningPage params={Promise.resolve({ id: "1", citationId: "c1" })} />
        </ProjectShell>
      </StrictMode>
    );

    expect(await screen.findByText(/include:\s*matches all criteria/i)).toBeInTheDocument();
    expect(mockedApi.generateSuggestion).toHaveBeenCalledTimes(1);
  });

  it("shows the PICO criteria beside the abstract and skips the ones left blank", async () => {
    mockedApi.getReviewProject.mockResolvedValue({
      ...dualReviewProject,
      review_mode: "solo",
      criteria: {
        ...dualReviewProject.criteria,
        population: "Adults with type 2 diabetes",
        outcome: "HbA1c at 6 months",
      },
    });
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: null,
    });

    renderPage();

    const criteria = await screen.findByRole("region", { name: "Criteria" });
    expect(within(criteria).getByText("Adults with type 2 diabetes")).toBeInTheDocument();
    expect(within(criteria).getByText("HbA1c at 6 months")).toBeInTheDocument();
    expect(within(criteria).queryByText("Intervention")).not.toBeInTheDocument();
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

  it("hides the AI Suggestion and seals the Co-Reviewer's Decision while blind", async () => {
    mockedApi.getReviewProject.mockResolvedValue(dualReviewProject);
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      peer_screening_decision: {
        decision: "exclude",
        reason: "Wrong population",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      screening_blind: true,
      full_text: null,
    });

    renderPage();

    expect(
      await screen.findByText(/hidden until you record your own screening decision/i)
    ).toBeInTheDocument();
    // The tab is there so the Reviewer knows a second opinion is coming, but sealed.
    expect(screen.getByRole("heading", { name: /co-reviewer's decision/i })).toBeInTheDocument();
    expect(screen.getByText(/sealed until you record your own screening decision/i)).toBeInTheDocument();
    expect(screen.queryByText(/wrong population/i)).not.toBeInTheDocument();
  });

  it("shows the AI Suggestion and Co-Reviewer's Decision once revealed", async () => {
    mockedApi.getReviewProject.mockResolvedValue(dualReviewProject);
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: { decision: "include", reason: "Matches all criteria." },
      suggestion_unavailable_reason: null,
      screening_decision: {
        decision: "include",
        reason: "My take",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      peer_screening_decision: {
        decision: "exclude",
        reason: "Wrong population",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      screening_blind: false,
      full_text: null,
    });

    renderPage();

    expect(await screen.findByText(/include:\s*matches all criteria/i)).toBeInTheDocument();
    expect(await screen.findByText(/co-reviewer's decision/i)).toBeInTheDocument();
    expect(screen.getByText(/exclude:\s*wrong population/i)).toBeInTheDocument();
  });

  it("shows the Co-Reviewer's Decision as not yet recorded when only this Reviewer has decided", async () => {
    mockedApi.getReviewProject.mockResolvedValue(dualReviewProject);
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: { decision: "include", reason: "Matches all criteria." },
      suggestion_unavailable_reason: null,
      screening_decision: {
        decision: "include",
        reason: "My take",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      peer_screening_decision: null,
      screening_blind: false,
      full_text: null,
    });

    renderPage();

    expect(await screen.findByText(/co-reviewer's decision/i)).toBeInTheDocument();
    expect(screen.getByText(/not yet recorded/i)).toBeInTheDocument();
  });

  // Regression: ISSUE-001 — the Co-Reviewer saw the Owner's decision titled "Co-Reviewer's Decision"
  // Found by /qa on 2026-09-19
  // Report: .gstack/qa-reports/qa-report-localhost-2026-09-19.md
  it("names the Owner's decision as the Owner's when the viewer is the Co-Reviewer", async () => {
    mockedApi.getMe.mockResolvedValue({
      id: "co-reviewer-1",
      email: "co@example.com",
      created_at: "2026-01-01T00:00:00Z",
    });
    mockedApi.getReviewProject.mockResolvedValue(dualReviewProject);
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: { decision: "include", reason: "Matches all criteria." },
      suggestion_unavailable_reason: null,
      screening_decision: {
        decision: "include",
        reason: "My take",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      peer_screening_decision: {
        decision: "exclude",
        reason: "Wrong population",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      screening_blind: false,
      full_text: null,
    });

    renderPage();

    expect(await screen.findByRole("heading", { name: /owner's decision/i })).toBeInTheDocument();
    expect(screen.getByText(/exclude:\s*wrong population/i)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /co-reviewer's decision/i })).not.toBeInTheDocument();
  });

  it("names the sealed tab after the Owner when the viewer is the blind Co-Reviewer", async () => {
    mockedApi.getMe.mockResolvedValue({
      id: "co-reviewer-1",
      email: "co@example.com",
      created_at: "2026-01-01T00:00:00Z",
    });
    mockedApi.getReviewProject.mockResolvedValue(dualReviewProject);
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      peer_screening_decision: null,
      screening_blind: true,
      full_text: null,
    });

    renderPage();

    expect(await screen.findByRole("heading", { name: /owner's decision/i })).toBeInTheDocument();
    expect(screen.getByText(/sealed until you record your own screening decision/i)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /co-reviewer's decision/i })).not.toBeInTheDocument();
  });

  it("does not show a Co-Reviewer's Decision section in a Solo Review Project", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: { decision: "include", reason: "Matches all criteria." },
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: null,
    });

    renderPage();

    await screen.findByText(/include:\s*matches all criteria/i);
    expect(screen.queryByText(/co-reviewer's decision/i)).not.toBeInTheDocument();
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

  it("asks for a Full-Text Suggestion once a Full Text has been uploaded", async () => {
    mockedApi.getCitation
      .mockResolvedValueOnce({
        ...baseCitation,
        suggestion: null,
        suggestion_unavailable_reason: null,
        screening_decision: null,
        full_text: null,
      })
      .mockResolvedValue({
        ...baseCitation,
        suggestion: null,
        suggestion_unavailable_reason: null,
        screening_decision: null,
        full_text: parsedFullText,
        full_text_suggestion_needs_generation: true,
      });
    mockedApi.uploadFullText.mockResolvedValue(parsedFullText);
    mockedApi.generateFullTextSuggestion.mockResolvedValue({
      suggestion: suggestionWithSampleSize,
      suggestion_unavailable_reason: null,
    });

    renderPage();
    await screen.findByText(/no full text uploaded yet/i);
    chooseFile(/upload full text/i);

    expect(await screen.findByText(/include:\s*meets all criteria/i)).toBeInTheDocument();
    expect(mockedApi.generateFullTextSuggestion).toHaveBeenCalledTimes(1);
  });

  it("drops the old Full-Text Suggestion when the Full Text is replaced, and asks for a new one", async () => {
    mockedApi.getCitation
      .mockResolvedValueOnce({
        ...baseCitation,
        suggestion: null,
        suggestion_unavailable_reason: null,
        screening_decision: null,
        full_text: parsedFullText,
        full_text_suggestion: { decision: "exclude", reason: "Old reasoning.", extraction_values: [] },
      })
      .mockResolvedValue({
        ...baseCitation,
        suggestion: null,
        suggestion_unavailable_reason: null,
        screening_decision: null,
        full_text: parsedFullText,
        full_text_suggestion_needs_generation: true,
      });
    mockedApi.uploadFullText.mockResolvedValue(parsedFullText);
    mockedApi.generateFullTextSuggestion.mockResolvedValue({
      suggestion: suggestionWithSampleSize,
      suggestion_unavailable_reason: null,
    });

    renderPage();
    await screen.findByText(/exclude:\s*old reasoning/i);
    chooseFile(/replace full text/i);

    expect(await screen.findByText(/include:\s*meets all criteria/i)).toBeInTheDocument();
    expect(screen.queryByText(/old reasoning/i)).not.toBeInTheDocument();
    expect(mockedApi.generateFullTextSuggestion).toHaveBeenCalledTimes(1);
  });

  it("never shows a Full-Text Suggestion that was requested before the Full Text was replaced", async () => {
    const first = deferred<api.FullTextSuggestionOutcome>();
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: parsedFullText,
      full_text_suggestion_needs_generation: true,
    });
    mockedApi.uploadFullText.mockResolvedValue(parsedFullText);
    mockedApi.generateFullTextSuggestion
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce({
        suggestion: { decision: "include", reason: "New reasoning.", extraction_values: [] },
        suggestion_unavailable_reason: null,
      });

    renderPage();
    await screen.findByText(/preparing a full-text suggestion/i);
    chooseFile(/replace full text/i);
    expect(await screen.findByText(/include:\s*new reasoning/i)).toBeInTheDocument();

    await act(async () => {
      first.resolve({
        suggestion: { decision: "exclude", reason: "Old reasoning.", extraction_values: [] },
        suggestion_unavailable_reason: null,
      });
      await first.promise;
    });

    expect(screen.queryByText(/old reasoning/i)).not.toBeInTheDocument();
    expect(screen.getByText(/include:\s*new reasoning/i)).toBeInTheDocument();
    expect(mockedApi.generateFullTextSuggestion).toHaveBeenCalledTimes(2);
  });

  it("still gets a Full-Text Suggestion when an upload fails while one is being prepared", async () => {
    const first = deferred<api.FullTextSuggestionOutcome>();
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: parsedFullText,
      full_text_suggestion_needs_generation: true,
    });
    mockedApi.uploadFullText.mockRejectedValue(new Error("nope"));
    mockedApi.generateFullTextSuggestion
      .mockReturnValueOnce(first.promise)
      .mockResolvedValueOnce({ suggestion: suggestionWithSampleSize, suggestion_unavailable_reason: null });

    renderPage();
    await screen.findByText(/preparing a full-text suggestion/i);
    chooseFile(/replace full text/i);

    expect(await screen.findByText(/failed to upload full text/i)).toBeInTheDocument();
    expect(await screen.findByText(/include:\s*meets all criteria/i)).toBeInTheDocument();
    expect(screen.queryByText(/preparing a full-text suggestion/i)).not.toBeInTheDocument();
  });

  it("drops the old Full-Text Suggestion even when the page cannot read the new state", async () => {
    mockedApi.getCitation
      .mockResolvedValueOnce({
        ...baseCitation,
        suggestion: null,
        suggestion_unavailable_reason: null,
        screening_decision: null,
        full_text: parsedFullText,
        full_text_suggestion: { decision: "exclude", reason: "Old reasoning.", extraction_values: [] },
      })
      .mockRejectedValue(new Error("offline"));
    mockedApi.uploadFullText.mockResolvedValue(parsedFullText);

    renderPage();
    await screen.findByText(/exclude:\s*old reasoning/i);
    chooseFile(/replace full text/i);

    await waitFor(() => expect(mockedApi.uploadFullText).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByText(/old reasoning/i)).not.toBeInTheDocument());
    expect(await screen.findByText(/could not check for a full-text suggestion/i)).toBeInTheDocument();
    expect(mockedApi.generateFullTextSuggestion).not.toHaveBeenCalled();
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

  it("fetches and opens the Full Text file when View / Download is clicked", async () => {
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
    const blob = new Blob(["pdf-bytes"], { type: "application/pdf" });
    mockedApi.fetchFullTextFile.mockResolvedValue(blob);
    const createObjectURL = vi.fn().mockReturnValue("blob:mock-url");
    vi.stubGlobal("URL", { ...URL, createObjectURL });
    const windowOpen = vi.spyOn(window, "open").mockImplementation(() => null);

    renderPage();
    await screen.findByText("paper.pdf");
    fireEvent.click(screen.getByRole("button", { name: /view \/ download/i }));

    await waitFor(() =>
      expect(mockedApi.fetchFullTextFile).toHaveBeenCalledWith("1", "c1")
    );
    expect(createObjectURL).toHaveBeenCalledWith(blob);
    expect(windowOpen).toHaveBeenCalledWith("blob:mock-url", "_blank", "noreferrer");

    vi.unstubAllGlobals();
  });

  it("shows an error when fetching the Full Text file fails", async () => {
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
    mockedApi.fetchFullTextFile.mockRejectedValue(new Error("nope"));

    renderPage();
    await screen.findByText("paper.pdf");
    fireEvent.click(screen.getByRole("button", { name: /view \/ download/i }));

    expect(await screen.findByText(/failed to load full text/i)).toBeInTheDocument();
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

  it("shows the Full-Text Suggestion decision and reason", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: parsedFullText,
      full_text_suggestion: suggestionWithSampleSize,
      full_text_suggestion_unavailable_reason: null,
    });

    renderPage();

    expect(
      await screen.findByText(/include:\s*meets all criteria/i)
    ).toBeInTheDocument();
  });

  it("shows the citation at once, then the Full-Text Suggestion when it arrives", async () => {
    const generation = deferred<api.FullTextSuggestionOutcome>();
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: parsedFullText,
      full_text_suggestion_needs_generation: true,
      extraction_fields: [sampleSizeField],
    });
    mockedApi.generateFullTextSuggestion.mockReturnValue(generation.promise);

    renderPage();

    const group = within(await screen.findByRole("group", { name: /full-text decision/i }));
    expect(screen.getByLabelText("Sample size")).toHaveValue("");
    expect(await screen.findByText(/preparing a full-text suggestion/i)).toBeInTheDocument();

    generation.resolve({ suggestion: suggestionWithSampleSize, suggestion_unavailable_reason: null });

    expect(await screen.findByText(/include:\s*meets all criteria/i)).toBeInTheDocument();
    expect(screen.queryByText(/preparing a full-text suggestion/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Use suggested Sample size" })).toBeEnabled();
    // Arriving late fills nothing the Reviewer owns.
    expect(screen.getByLabelText("Sample size")).toHaveValue("");
    expect(group.getByLabelText("include")).not.toBeChecked();
  });

  it("says when the Full-Text Suggestion could not be generated, without retrying or blocking the forms", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: parsedFullText,
      full_text_suggestion_needs_generation: true,
    });
    mockedApi.generateFullTextSuggestion.mockResolvedValue({
      suggestion: null,
      suggestion_unavailable_reason: "generation_failed",
    });

    renderPage();
    const group = within(await screen.findByRole("group", { name: /full-text decision/i }));

    expect(await screen.findByText(/generating a full-text suggestion failed/i)).toBeInTheDocument();
    fireEvent.click(group.getByLabelText("include"));
    expect(group.getByLabelText("include")).toBeChecked();
    expect(mockedApi.generateFullTextSuggestion).toHaveBeenCalledTimes(1);
  });

  it("treats a failed request for the Full-Text Suggestion as a generation failure", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: parsedFullText,
      full_text_suggestion_needs_generation: true,
    });
    mockedApi.generateFullTextSuggestion.mockRejectedValue(new Error("network"));

    renderPage();

    expect(await screen.findByText(/generating a full-text suggestion failed/i)).toBeInTheDocument();
    expect(mockedApi.generateFullTextSuggestion).toHaveBeenCalledTimes(1);
  });

  it("does not ask for a Full-Text Suggestion that exists or cannot be made", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: parsedFullText,
      full_text_suggestion: suggestionWithSampleSize,
      full_text_suggestion_needs_generation: false,
    });

    renderPage();

    expect(await screen.findByText(/include:\s*meets all criteria/i)).toBeInTheDocument();
    expect(mockedApi.generateFullTextSuggestion).not.toHaveBeenCalled();
  });

  it("sends one request for the Full-Text Suggestion under React Strict Mode", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: parsedFullText,
      full_text_suggestion_needs_generation: true,
    });
    mockedApi.generateFullTextSuggestion.mockResolvedValue({
      suggestion: suggestionWithSampleSize,
      suggestion_unavailable_reason: null,
    });

    render(
      <StrictMode>
        <ProjectShell reviewProjectId="1">
          <CitationScreeningPage params={Promise.resolve({ id: "1", citationId: "c1" })} />
        </ProjectShell>
      </StrictMode>
    );

    expect(await screen.findByText(/include:\s*meets all criteria/i)).toBeInTheDocument();
    expect(mockedApi.generateFullTextSuggestion).toHaveBeenCalledTimes(1);
  });

  it("looks again when the Full Text was replaced while the model was reading the old one", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: parsedFullText,
      full_text_suggestion_needs_generation: true,
    });
    mockedApi.generateFullTextSuggestion
      .mockResolvedValueOnce({ suggestion: null, suggestion_unavailable_reason: null })
      .mockResolvedValueOnce({
        suggestion: suggestionWithSampleSize,
        suggestion_unavailable_reason: null,
      });

    renderPage();

    expect(await screen.findByText(/include:\s*meets all criteria/i)).toBeInTheDocument();
    expect(mockedApi.generateFullTextSuggestion).toHaveBeenCalledTimes(2);
  });

  it("ends the loading state when the replacement refresh fails", async () => {
    mockedApi.getCitation
      .mockResolvedValueOnce({
        ...baseCitation,
        suggestion: null,
        suggestion_unavailable_reason: null,
        screening_decision: null,
        full_text: parsedFullText,
        full_text_suggestion_needs_generation: true,
      })
      .mockRejectedValueOnce(new Error("network"));
    mockedApi.generateFullTextSuggestion.mockResolvedValue({
      suggestion: null,
      suggestion_unavailable_reason: null,
    });

    renderPage();

    expect(await screen.findByText(/generating a full-text suggestion failed/i)).toBeInTheDocument();
    expect(screen.queryByText(/preparing a full-text suggestion/i)).not.toBeInTheDocument();
  });

  it("leaves the Full-Text Decision unchosen even when a Full-Text Suggestion exists", async () => {
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
        decision: "exclude",
        reason: "Wrong study design.",
        extraction_values: [],
      },
    });

    renderPage();
    const group = within(await screen.findByRole("group", { name: /full-text decision/i }));

    expect(group.getByLabelText("include")).not.toBeChecked();
    expect(group.getByLabelText("exclude")).not.toBeChecked();
    expect(group.getByLabelText("maybe")).not.toBeChecked();
    expect(group.queryByLabelText(/reason/i)).not.toBeInTheDocument();
  });

  it("asks for a choice instead of saving a Full-Text Decision nobody made", async () => {
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

    renderPage();
    await screen.findByRole("group", { name: /full-text decision/i });
    fireEvent.click(screen.getByRole("button", { name: /save full-text decision/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Choose Include, Exclude or Maybe first."
    );
    expect(mockedApi.recordFullTextDecision).not.toHaveBeenCalled();
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

  it("leaves the extraction input empty and offers the suggested value beside it", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: parsedFullText,
      full_text_suggestion: suggestionWithSampleSize,
      extraction_fields: [sampleSizeField],
    });

    renderPage();

    expect(await screen.findByLabelText("Sample size")).toHaveValue("");
    expect(screen.getByText(/suggested:\s*120 participants/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Use suggested Sample size" })).toBeEnabled();
    // The value is shown once, beside its field, not again in the suggestion note.
    expect(screen.getAllByText(/120 participants/)).toHaveLength(1);
    expect(mockedApi.recordExtractionValue).not.toHaveBeenCalled();
  });

  it("disables Use once the input already holds the suggested value", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: parsedFullText,
      full_text_suggestion: suggestionWithSampleSize,
      extraction_fields: [sampleSizeField],
    });

    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Use suggested Sample size" }));

    expect(screen.getByLabelText("Sample size")).toHaveValue("120 participants");
    expect(screen.getByRole("button", { name: "Use suggested Sample size" })).toBeDisabled();
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

  it("records an AI-proposed extraction value only after the Reviewer uses it and saves", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: parsedFullText,
      full_text_suggestion: suggestionWithSampleSize,
      extraction_fields: [sampleSizeField],
    });
    mockedApi.recordExtractionValue.mockResolvedValue({
      extraction_field_id: "f1",
      name: "Sample size",
      value: "120 participants",
      created_at: "2026-01-02T00:00:00Z",
      updated_at: "2026-01-02T00:00:00Z",
    });

    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Use suggested Sample size" }));
    expect(mockedApi.recordExtractionValue).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(mockedApi.recordExtractionValue).toHaveBeenCalledWith("1", "c1", "f1", {
        value: "120 participants",
      })
    );
  });

  it("lets the Reviewer correct a used AI value before saving", async () => {
    mockedApi.getCitation.mockResolvedValue({
      ...baseCitation,
      suggestion: null,
      suggestion_unavailable_reason: null,
      screening_decision: null,
      full_text: parsedFullText,
      full_text_suggestion: suggestionWithSampleSize,
      extraction_fields: [sampleSizeField],
    });
    mockedApi.recordExtractionValue.mockResolvedValue({
      extraction_field_id: "f1",
      name: "Sample size",
      value: "118 participants (corrected)",
      created_at: "2026-01-02T00:00:00Z",
      updated_at: "2026-01-02T00:00:00Z",
    });

    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: "Use suggested Sample size" }));
    const input = screen.getByLabelText("Sample size");
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
