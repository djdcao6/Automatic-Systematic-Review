import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";
import type { SearchTerms } from "@/lib/api";

import { SearchTermsPanel } from "./SearchTermsPanel";

vi.mock("@/lib/api");

const mockedApi = vi.mocked(api);

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

const sampleTerms = {
  population_terms: ["adults", "elderly"],
  intervention_terms: ["metformin"],
  comparison_terms: [],
  outcome_terms: ["hba1c"],
  combined_query: "(adults OR elderly) AND (metformin) AND (hba1c)",
};

describe("SearchTermsPanel", () => {
  beforeEach(() => {
    mockedApi.getSearchTerms.mockResolvedValue(null);
  });

  it("generates and displays search terms grouped by PICO concept", async () => {
    mockedApi.generateSearchTerms.mockResolvedValue(sampleTerms);

    render(<SearchTermsPanel reviewProjectId="1" />);

    fireEvent.click(await screen.findByRole("button", { name: /suggest search terms/i }));

    expect(await screen.findByText("adults")).toBeInTheDocument();
    expect(screen.getByText("elderly")).toBeInTheDocument();
    expect(screen.getByText("metformin")).toBeInTheDocument();
    expect(screen.getByText("hba1c")).toBeInTheDocument();
    expect(screen.getByText(/combined query/i)).toHaveTextContent(sampleTerms.combined_query);
    expect(mockedApi.generateSearchTerms).toHaveBeenCalledWith("1");
  });

  it("shows a clear message when generation is blocked by no populated PICO field", async () => {
    mockedApi.generateSearchTerms.mockRejectedValue(
      new Error("At least one PICO field must be populated to generate Search Terms")
    );

    render(<SearchTermsPanel reviewProjectId="1" />);

    fireEvent.click(await screen.findByRole("button", { name: /suggest search terms/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/at least one pico field/i);
  });

  it("adds a term to a concept and updates the combined string", async () => {
    mockedApi.getSearchTerms.mockResolvedValue(sampleTerms);
    mockedApi.updateSearchTerms.mockResolvedValue({
      ...sampleTerms,
      comparison_terms: ["placebo"],
      combined_query: "(adults OR elderly) AND (metformin) AND (placebo) AND (hba1c)",
    });

    render(<SearchTermsPanel reviewProjectId="1" />);
    await screen.findByText("adults");

    const input = screen.getByLabelText(/add comparison term/i);
    fireEvent.change(input, { target: { value: "placebo" } });
    fireEvent.submit(input.closest("form") as HTMLFormElement);

    await waitFor(() =>
      expect(mockedApi.updateSearchTerms).toHaveBeenCalledWith("1", {
        population_terms: sampleTerms.population_terms,
        intervention_terms: sampleTerms.intervention_terms,
        comparison_terms: ["placebo"],
        outcome_terms: sampleTerms.outcome_terms,
      })
    );
    expect(await screen.findByText("placebo")).toBeInTheDocument();
    expect(screen.getByText(/combined query/i)).toHaveTextContent(
      "(adults OR elderly) AND (metformin) AND (placebo) AND (hba1c)"
    );
  });

  it("removes a term from a concept and updates the combined string", async () => {
    mockedApi.getSearchTerms.mockResolvedValue(sampleTerms);
    mockedApi.updateSearchTerms.mockResolvedValue({
      ...sampleTerms,
      population_terms: ["elderly"],
      combined_query: "(elderly) AND (metformin) AND (hba1c)",
    });

    render(<SearchTermsPanel reviewProjectId="1" />);
    const adultsItem = (await screen.findByText("adults")).closest("li") as HTMLElement;

    fireEvent.click(within(adultsItem).getByRole("button", { name: /remove/i }));

    await waitFor(() =>
      expect(mockedApi.updateSearchTerms).toHaveBeenCalledWith("1", {
        population_terms: ["elderly"],
        intervention_terms: sampleTerms.intervention_terms,
        comparison_terms: sampleTerms.comparison_terms,
        outcome_terms: sampleTerms.outcome_terms,
      })
    );
    await waitFor(() => expect(screen.queryByText("adults")).not.toBeInTheDocument());
    expect(screen.getByText(/combined query/i)).toHaveTextContent(
      "(elderly) AND (metformin) AND (hba1c)"
    );
  });

  it("disables edit and generate controls while a save is in flight, to avoid racing edits", async () => {
    mockedApi.getSearchTerms.mockResolvedValue(sampleTerms);
    let resolveUpdate!: (value: typeof sampleTerms) => void;
    mockedApi.updateSearchTerms.mockReturnValue(
      new Promise((resolve) => {
        resolveUpdate = resolve;
      })
    );

    render(<SearchTermsPanel reviewProjectId="1" />);
    const adultsItem = (await screen.findByText("adults")).closest("li") as HTMLElement;

    fireEvent.click(within(adultsItem).getByRole("button", { name: /remove/i }));

    await waitFor(() => expect(mockedApi.updateSearchTerms).toHaveBeenCalledTimes(1));
    expect(within(adultsItem).getByRole("button", { name: /remove/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /regenerate/i })).toBeDisabled();

    resolveUpdate({ ...sampleTerms, population_terms: ["elderly"] });

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /regenerate/i })).not.toBeDisabled()
    );
  });

  it("regenerates and replaces the currently displayed terms", async () => {
    mockedApi.getSearchTerms.mockResolvedValue(sampleTerms);
    mockedApi.generateSearchTerms.mockResolvedValue({
      population_terms: ["children"],
      intervention_terms: [],
      comparison_terms: [],
      outcome_terms: [],
      combined_query: "(children)",
    });

    render(<SearchTermsPanel reviewProjectId="1" />);
    await screen.findByText("adults");

    fireEvent.click(screen.getByRole("button", { name: /regenerate/i }));

    expect(await screen.findByText("children")).toBeInTheDocument();
    expect(screen.queryByText("adults")).not.toBeInTheDocument();
    expect(screen.queryByText("metformin")).not.toBeInTheDocument();
    expect(mockedApi.generateSearchTerms).toHaveBeenCalledWith("1");
  });

  it("shows an error when loading previously saved search terms fails", async () => {
    mockedApi.getSearchTerms.mockRejectedValue(new Error("boom"));

    render(<SearchTermsPanel reviewProjectId="1" />);

    expect(await screen.findByRole("alert")).toHaveTextContent(/failed to load/i);
  });

  it("ignores a stale response after reviewProjectId changes before it resolves", async () => {
    const first = deferred<SearchTerms | null>();
    const second = deferred<SearchTerms | null>();
    mockedApi.getSearchTerms.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);

    const { rerender } = render(<SearchTermsPanel reviewProjectId="1" />);
    rerender(<SearchTermsPanel reviewProjectId="2" />);

    await act(async () => {
      second.resolve({ ...sampleTerms, population_terms: ["project-b-term"] });
    });
    expect(await screen.findByText("project-b-term")).toBeInTheDocument();

    await act(async () => {
      first.resolve({ ...sampleTerms, population_terms: ["project-a-term"] });
    });
    expect(screen.queryByText("project-a-term")).not.toBeInTheDocument();
  });
});
