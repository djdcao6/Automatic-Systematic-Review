import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";

import CitationScreeningPage from "./page";

vi.mock("@/lib/api");

const mockedApi = vi.mocked(api);

const stamp = "2026-01-01T00:00:00Z";

const project = {
  id: "1",
  name: "My Review",
  criteria_locked: false,
  merge_mode: "combine" as const,
  review_mode: "solo" as const,
  owner_reviewer_id: "owner-1",
  co_reviewer_id: null,
  created_at: stamp,
  criteria: {
    population: null,
    intervention: null,
    comparison: null,
    outcome: null,
    exclusion_rules: [],
    notes: null,
  },
  citations_needing_decision: 1,
};
const dualProject = {
  ...project,
  review_mode: "dual" as const,
  co_reviewer_id: "co-reviewer-1",
};

const listed = (id: string, title: string) => ({
  id,
  title,
  abstract: `Abstract of ${title}.`,
  authors: ["Doe J"],
  year: 2020,
  source: ["PubMed"],
  needs_abstract: false,
  blocked_pending_co_reviewer: false,
});
// By default this is the middle citation of three: the backend reports where it
// sits and which citations are either side, so the page never loads the list.
const detail = (overrides = {}) => ({
  ...listed("c1", "Metformin RCT"),
  position: 2,
  total: 3,
  previous_citation_id: "c0" as string | null,
  next_citation_id: "c2" as string | null,
  peer_screening_decision: null,
  screening_blind: false,
  screening_resolved: false,
  full_text_decision: null,
  full_text_suggestion: null,
  full_text_suggestion_unavailable_reason: null,
  extraction_fields: [],
  extraction_values: [],
  suggestion: null,
  suggestion_unavailable_reason: null,
  screening_decision: null,
  full_text: null,
  ...overrides,
});

const decisionRecord = (decision: "include" | "exclude" | "maybe") => ({
  decision,
  reason: null,
  created_at: stamp,
  updated_at: stamp,
});

function renderPage(citationId = "c1") {
  return render(<CitationScreeningPage params={Promise.resolve({ id: "1", citationId })} />);
}

function renderNext(rerender: ReturnType<typeof render>["rerender"], citationId: string) {
  rerender(<CitationScreeningPage params={Promise.resolve({ id: "1", citationId })} />);
}

describe("CitationScreeningPage screening frame", () => {
  beforeEach(() => {
    mockedApi.getReviewProject.mockReset();
    mockedApi.getCitation.mockReset();
    mockedApi.listCitations.mockReset();
    mockedApi.recordScreeningDecision.mockReset();
    mockedApi.getReviewProject.mockResolvedValue(project);
    mockedApi.getCitation.mockResolvedValue(detail());
    mockedApi.recordScreeningDecision.mockResolvedValue(decisionRecord("include"));
  });

  describe("folio", () => {
    it("shows where this citation sits in the project's list and the way to its neighbours", async () => {
      renderPage();

      const count = (await screen.findByText("of 3")).parentElement;
      expect(count).toHaveTextContent("2 of 3");
      expect(screen.getByRole("link", { name: "Previous" })).toHaveAttribute(
        "href",
        "/review-projects/1/citations/c0"
      );
      expect(screen.getByRole("link", { name: "Next" })).toHaveAttribute(
        "href",
        "/review-projects/1/citations/c2"
      );
    });

    it("reports progress as the citations that already have a decision", async () => {
      renderPage();

      const bar = await screen.findByRole("progressbar", { name: /screening progress/i });
      expect(bar).toHaveAttribute("aria-valuenow", "2");
      expect(bar).toHaveAttribute("aria-valuemax", "3");
    });

    it("refreshes the progress once a decision is recorded", async () => {
      mockedApi.getReviewProject
        .mockResolvedValueOnce({ ...project, citations_needing_decision: 1 })
        .mockResolvedValue({ ...project, citations_needing_decision: 0 });
      renderPage();

      await screen.findByRole("progressbar");
      fireEvent.click(screen.getByLabelText("include"));
      fireEvent.click(screen.getByRole("button", { name: /save decision/i }));

      await waitFor(() =>
        expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "3")
      );
    });

    it("names the review mode beside the count", async () => {
      renderPage();
      expect(await screen.findByText("Solo review")).toBeInTheDocument();
    });

    it("takes the neighbours from the citation the backend returned", async () => {
      mockedApi.getCitation.mockResolvedValue(
        detail({ previous_citation_id: "c9", next_citation_id: "c7" })
      );
      renderPage();

      expect(await screen.findByRole("link", { name: "Previous" })).toHaveAttribute(
        "href",
        "/review-projects/1/citations/c9"
      );
      expect(screen.getByRole("link", { name: "Next" })).toHaveAttribute(
        "href",
        "/review-projects/1/citations/c7"
      );
    });

    it("has no previous link on the first citation", async () => {
      mockedApi.getCitation.mockResolvedValue(
        detail({ id: "c0", title: "First trial", position: 1, previous_citation_id: null })
      );
      renderPage("c0");

      await screen.findByText("of 3");
      expect(screen.queryByRole("link", { name: "Previous" })).not.toBeInTheDocument();
      expect(screen.getByRole("link", { name: "Next" })).toBeInTheDocument();
    });

    it("leaves the folio out for a citation that has no place in the list", async () => {
      mockedApi.getCitation.mockResolvedValue(
        detail({ position: null, previous_citation_id: null, next_citation_id: null })
      );
      renderPage();

      expect(await screen.findByRole("heading", { name: "Metformin RCT" })).toBeInTheDocument();
      expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    });

    it("leaves the folio out, and the page working, until the project has loaded", async () => {
      mockedApi.getReviewProject.mockRejectedValue(new Error("down"));
      renderPage();

      expect(await screen.findByRole("heading", { name: "Metformin RCT" })).toBeInTheDocument();
      expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    });
  });

  describe("moving between citations", () => {
    it("starts the next citation clean instead of carrying over the last one's form", async () => {
      mockedApi.getCitation.mockImplementation(async (_project, id) =>
        detail({ id, title: id === "c1" ? "Metformin RCT" : "Third trial" })
      );
      const { rerender } = renderPage();

      await screen.findByRole("heading", { name: "Metformin RCT" });
      fireEvent.click(screen.getByLabelText("exclude"));
      fireEvent.change(screen.getByLabelText(/reason/i), {
        target: { value: "Wrong population." },
      });
      fireEvent.click(screen.getByRole("button", { name: /save decision/i }));
      await screen.findByText(/decision saved/i);

      renderNext(rerender, "c2");

      expect(await screen.findByRole("heading", { name: "Third trial" })).toBeInTheDocument();
      expect(screen.queryByText(/decision saved/i)).not.toBeInTheDocument();
      expect(screen.getByLabelText(/reason/i)).toHaveValue("");
      expect(screen.getByLabelText("exclude")).not.toBeChecked();
    });

    it("fetches the project once, and never downloads the whole citation list", async () => {
      mockedApi.getCitation.mockImplementation(async (_project, id) => detail({ id }));
      const { rerender } = renderPage();
      await screen.findByText("of 3");

      renderNext(rerender, "c2");
      await waitFor(() => expect(mockedApi.getCitation).toHaveBeenCalledWith("1", "c2"));

      expect(mockedApi.getReviewProject).toHaveBeenCalledTimes(1);
      expect(mockedApi.listCitations).not.toHaveBeenCalled();
    });
  });

  describe("keyboard", () => {
    it("advertises I, E and M on the screening decision, and nothing on the full-text decision", async () => {
      mockedApi.getCitation.mockResolvedValue(
        detail({
          full_text: {
            original_filename: "paper.pdf",
            parse_status: "parsed",
            created_at: stamp,
            updated_at: stamp,
          },
        })
      );
      renderPage();

      const screening = within(await screen.findByRole("group", { name: "Screening Decision" }));
      expect(screening.getByLabelText("include")).toHaveAttribute("aria-keyshortcuts", "i");
      expect(screening.getByLabelText("exclude")).toHaveAttribute("aria-keyshortcuts", "e");
      expect(screening.getByLabelText("maybe")).toHaveAttribute("aria-keyshortcuts", "m");

      const fullText = within(screen.getByRole("group", { name: "Full-Text Decision" }));
      expect(fullText.getByLabelText("include")).not.toHaveAttribute("aria-keyshortcuts");
    });

    it("chooses a decision on I, E and M", async () => {
      renderPage();
      await screen.findByRole("group", { name: "Screening Decision" });

      fireEvent.keyDown(document.body, { key: "i" });
      expect(screen.getByLabelText("include")).toBeChecked();
      fireEvent.keyDown(document.body, { key: "e" });
      expect(screen.getByLabelText("exclude")).toBeChecked();
      fireEvent.keyDown(document.body, { key: "m" });
      expect(screen.getByLabelText("maybe")).toBeChecked();
    });

    it("does not change the decision when the letters are typed into the reason", async () => {
      renderPage();
      const reason = await screen.findByLabelText(/reason/i);

      fireEvent.keyDown(reason, { key: "e" });

      expect(screen.getByLabelText("exclude")).not.toBeChecked();
    });

    it("starts with no decision chosen, so a stray keystroke cannot record one", async () => {
      renderPage();
      await screen.findByRole("group", { name: "Screening Decision" });

      for (const option of ["include", "exclude", "maybe"]) {
        expect(screen.getByLabelText(option)).not.toBeChecked();
      }
    });

    it("asks for a choice, and records nothing, when saved before one is made", async () => {
      renderPage();
      await screen.findByRole("group", { name: "Screening Decision" });

      fireEvent.keyDown(document.body, { key: "Enter", ctrlKey: true });

      expect(await screen.findByText(/choose include, exclude or maybe/i)).toBeInTheDocument();
      expect(mockedApi.recordScreeningDecision).not.toHaveBeenCalled();
      expect(screen.queryByText(/decision saved/i)).not.toBeInTheDocument();
    });

    it("drops the prompt as soon as a choice is made", async () => {
      renderPage();
      await screen.findByRole("group", { name: "Screening Decision" });
      fireEvent.click(screen.getByRole("button", { name: /save decision/i }));
      await screen.findByText(/choose include, exclude or maybe/i);

      fireEvent.keyDown(document.body, { key: "m" });

      expect(screen.queryByText(/choose include, exclude or maybe/i)).not.toBeInTheDocument();
    });

    it("records the decision on Ctrl+Enter from inside the reason field", async () => {
      renderPage();
      const reason = await screen.findByLabelText(/reason/i);

      fireEvent.keyDown(document.body, { key: "e" });
      fireEvent.change(reason, { target: { value: "Wrong population." } });
      fireEvent.keyDown(reason, { key: "Enter", ctrlKey: true });

      await waitFor(() =>
        expect(mockedApi.recordScreeningDecision).toHaveBeenCalledWith("1", "c1", {
          decision: "exclude",
          reason: "Wrong population.",
        })
      );
    });
  });

  describe("reading page", () => {
    it("shows the sources and authors above the abstract", async () => {
      mockedApi.getCitation.mockResolvedValue(
        detail({ authors: ["Doe J", "Roe P"], year: 2020, source: ["Embase", "PubMed"] })
      );
      renderPage();

      expect(await screen.findByText("Embase, PubMed")).toBeInTheDocument();
      expect(screen.getByText(/Doe J, Roe P/)).toBeInTheDocument();
      expect(screen.getByText(/2020/)).toBeInTheDocument();
    });

    it("flags a citation that has no abstract", async () => {
      mockedApi.getCitation.mockResolvedValue(
        detail({
          abstract: null,
          needs_abstract: true,
          suggestion_unavailable_reason: "missing_abstract",
        })
      );
      renderPage();

      expect(await screen.findByText("No abstract", { selector: ".flag" })).toBeInTheDocument();
    });

    it("does not flag a citation that has an abstract", async () => {
      renderPage();

      await screen.findByRole("heading", { name: "Metformin RCT" });
      expect(screen.queryByText("No abstract", { selector: ".flag" })).not.toBeInTheDocument();
    });
  });

  describe("criteria margin", () => {
    it("marks the Criteria as locked and lists the exclusion rules", async () => {
      mockedApi.getReviewProject.mockResolvedValue({
        ...project,
        criteria_locked: true,
        criteria: {
          ...project.criteria,
          population: "Adults with type 2 diabetes",
          exclusion_rules: ["Non-English language"],
        },
      });
      renderPage();

      const criteria = within(await screen.findByRole("region", { name: "Criteria" }));
      expect(criteria.getByText("locked")).toBeInTheDocument();
      expect(criteria.getByText("Exclude if")).toBeInTheDocument();
      expect(criteria.getByText("Non-English language")).toBeInTheDocument();
    });

    it("does not mark the Criteria as locked before the first decision", async () => {
      mockedApi.getReviewProject.mockResolvedValue({
        ...project,
        criteria: { ...project.criteria, population: "Adults with type 2 diabetes" },
      });
      renderPage();

      const criteria = within(await screen.findByRole("region", { name: "Criteria" }));
      expect(criteria.queryByText("locked")).not.toBeInTheDocument();
    });
  });

  describe("Co-Reviewer", () => {
    beforeEach(() => {
      mockedApi.getReviewProject.mockResolvedValue(dualProject);
    });

    it("says a Conflict is held when the two decisions differ", async () => {
      mockedApi.getCitation.mockResolvedValue(
        detail({
          screening_decision: decisionRecord("include"),
          peer_screening_decision: decisionRecord("exclude"),
        })
      );
      renderPage();

      expect(await screen.findByRole("status")).toHaveTextContent(/held as a conflict/i);
    });

    it("says nothing when the decisions agree", async () => {
      mockedApi.getCitation.mockResolvedValue(
        detail({
          screening_decision: decisionRecord("include"),
          peer_screening_decision: decisionRecord("include"),
        })
      );
      renderPage();

      await screen.findByText(/co-reviewer's decision/i);
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });

    it("says nothing once the Owner has resolved the Conflict", async () => {
      mockedApi.getCitation.mockResolvedValue(
        detail({
          screening_decision: decisionRecord("include"),
          peer_screening_decision: decisionRecord("exclude"),
          screening_resolved: true,
        })
      );
      renderPage();

      await screen.findByText(/co-reviewer's decision/i);
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });

    it("says nothing while this Reviewer has not decided yet", async () => {
      mockedApi.getCitation.mockResolvedValue(
        detail({ screening_blind: true, peer_screening_decision: decisionRecord("exclude") })
      );
      renderPage();

      await screen.findByText(/sealed until you record/i);
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });
  });
});
