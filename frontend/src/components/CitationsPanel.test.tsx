import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";
import type { Citation } from "@/lib/api";

import { CitationsPanel } from "./CitationsPanel";

vi.mock("@/lib/api");

const mockedApi = vi.mocked(api);

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

function citation(id: string, title: string): Citation {
  return {
    id,
    title,
    abstract: "Abstract",
    authors: [],
    year: 2022,
    source: [],
    needs_abstract: false,
    blocked_pending_co_reviewer: false,
  };
}

describe("CitationsPanel", () => {
  beforeEach(() => {
    mockedApi.uploadCitations.mockResolvedValue({ created: 1, skipped: [] });
  });

  it("lists citations and flags ones missing an abstract", async () => {
    mockedApi.listCitations.mockResolvedValue([
      {
        id: "1",
        title: "Has Abstract",
        abstract: "An abstract",
        authors: ["Jane Doe"],
        year: 2020,
        source: ["PubMed"],
        needs_abstract: false,
        blocked_pending_co_reviewer: false,
      },
      {
        id: "2",
        title: "Missing Abstract",
        abstract: null,
        authors: [],
        year: null,
        source: [],
        needs_abstract: true,
        blocked_pending_co_reviewer: false,
      },
    ]);

    render(<CitationsPanel reviewProjectId="1" />);

    expect(await screen.findByText("Has Abstract")).toBeInTheDocument();
    expect(screen.getByText("Missing Abstract")).toBeInTheDocument();
    expect(screen.getByText(/needs abstract/i)).toBeInTheDocument();
  });

  it("flags a citation blocked pending a replacement Co-Reviewer", async () => {
    mockedApi.listCitations.mockResolvedValue([
      {
        id: "1",
        title: "Awaiting Replacement",
        abstract: "An abstract",
        authors: [],
        year: 2020,
        source: ["PubMed"],
        needs_abstract: false,
        blocked_pending_co_reviewer: true,
      },
    ]);

    render(<CitationsPanel reviewProjectId="1" />);

    expect(await screen.findByText("Awaiting Replacement")).toBeInTheDocument();
    expect(screen.getByText(/awaiting a replacement co-reviewer/i)).toBeInTheDocument();
  });

  it("uploads a file and refreshes the list", async () => {
    mockedApi.listCitations
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([
        {
          id: "1",
          title: "New Citation",
          abstract: "Abstract",
          authors: [],
          year: 2022,
          source: [],
          needs_abstract: false,
          blocked_pending_co_reviewer: false,
        },
      ]);

    render(<CitationsPanel reviewProjectId="1" />);

    await waitFor(() => expect(mockedApi.listCitations).toHaveBeenCalledTimes(1));

    const file = new File(["title\nA\n"], "citations.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText(/upload ris or csv file/i), {
      target: { files: [file] },
    });

    expect(await screen.findByText("New Citation")).toBeInTheDocument();
    expect(mockedApi.uploadCitations).toHaveBeenCalledWith("1", file);
  });

  it("renders only the active citations the API returns after a duplicate merge", async () => {
    mockedApi.listCitations.mockResolvedValue([
      {
        id: "1",
        title: "Surviving Citation",
        abstract: "An abstract",
        authors: ["Jane Doe"],
        year: 2020,
        source: ["PubMed", "Embase"],
        needs_abstract: false,
        blocked_pending_co_reviewer: false,
      },
    ]);

    render(<CitationsPanel reviewProjectId="1" />);

    expect(await screen.findByText("Surviving Citation")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });

  it("notifies the parent after a successful upload so counts can refresh", async () => {
    mockedApi.listCitations.mockResolvedValueOnce([]).mockResolvedValueOnce([
      {
        id: "1",
        title: "New Citation",
        abstract: "Abstract",
        authors: [],
        year: 2022,
        source: [],
        needs_abstract: false,
        blocked_pending_co_reviewer: false,
      },
    ]);
    const onCitationsChanged = vi.fn();

    render(<CitationsPanel reviewProjectId="1" onCitationsChanged={onCitationsChanged} />);

    await waitFor(() => expect(mockedApi.listCitations).toHaveBeenCalledTimes(1));

    const file = new File(["title\nA\n"], "citations.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText(/upload ris or csv file/i), {
      target: { files: [file] },
    });

    await waitFor(() => expect(onCitationsChanged).toHaveBeenCalledTimes(1));
  });

  // Regression: ISSUE-002 — the upload result's `skipped` rows were never
  // shown, so a row dropped for a missing title vanished without a word.
  // Found by /qa on 2026-09-19
  // Report: .gstack/qa-reports/qa-report-localhost-2026-09-19.md
  it("tells the Reviewer which rows an upload skipped and why", async () => {
    mockedApi.listCitations.mockResolvedValue([]);
    mockedApi.uploadCitations.mockResolvedValue({
      created: 1,
      skipped: [
        { row: 1, reason: "missing title" },
        { row: 4, reason: "unreadable year" },
      ],
    });

    render(<CitationsPanel reviewProjectId="1" />);
    await waitFor(() => expect(mockedApi.listCitations).toHaveBeenCalledTimes(1));

    const file = new File(["title\n"], "citations.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText(/upload ris or csv file/i), {
      target: { files: [file] },
    });

    expect(await screen.findByText(/2 rows skipped/i)).toBeInTheDocument();
    expect(screen.getByText("Row 1: missing title")).toBeInTheDocument();
    expect(screen.getByText("Row 4: unreadable year")).toBeInTheDocument();
  });

  it("uses the singular for one skipped row and shows nothing when none were skipped", async () => {
    mockedApi.listCitations.mockResolvedValue([]);
    mockedApi.uploadCitations
      .mockResolvedValueOnce({ created: 0, skipped: [{ row: 2, reason: "missing title" }] })
      .mockResolvedValueOnce({ created: 1, skipped: [] });

    render(<CitationsPanel reviewProjectId="1" />);
    await waitFor(() => expect(mockedApi.listCitations).toHaveBeenCalledTimes(1));

    const input = screen.getByLabelText(/upload ris or csv file/i);
    const file = new File(["title\n"], "citations.csv", { type: "text/csv" });

    fireEvent.change(input, { target: { files: [file] } });
    expect(await screen.findByText(/1 row skipped/i)).toBeInTheDocument();

    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(screen.queryByText(/row skipped/i)).not.toBeInTheDocument());
    expect(screen.queryByText(/missing title/i)).not.toBeInTheDocument();
  });

  it("drops a previous upload's skipped rows when the next upload is rejected", async () => {
    mockedApi.listCitations.mockResolvedValue([]);
    mockedApi.uploadCitations
      .mockResolvedValueOnce({ created: 0, skipped: [{ row: 1, reason: "missing title" }] })
      .mockRejectedValueOnce(new Error("File must be .ris or .csv"));

    render(<CitationsPanel reviewProjectId="1" />);
    await waitFor(() => expect(mockedApi.listCitations).toHaveBeenCalledTimes(1));

    const input = screen.getByLabelText(/upload ris or csv file/i);
    const file = new File(["title\n"], "citations.csv", { type: "text/csv" });

    fireEvent.change(input, { target: { files: [file] } });
    expect(await screen.findByText("Row 1: missing title")).toBeInTheDocument();

    fireEvent.change(input, { target: { files: [file] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("File must be .ris or .csv");
    expect(screen.queryByText("Row 1: missing title")).not.toBeInTheDocument();
  });

  // Regression: ISSUE-003 — the panel's catch block replaced the backend's
  // reason ("File must be .ris or .csv") with a hardcoded generic string.
  // Found by /qa on 2026-09-19
  // Report: .gstack/qa-reports/qa-report-localhost-2026-09-19.md
  it("shows the backend's reason when an upload is rejected", async () => {
    mockedApi.listCitations.mockResolvedValue([]);
    mockedApi.uploadCitations.mockRejectedValue(new Error("File must be .ris or .csv"));

    render(<CitationsPanel reviewProjectId="1" />);
    await waitFor(() => expect(mockedApi.listCitations).toHaveBeenCalledTimes(1));

    const file = new File(["not a citation file"], "notes.txt", { type: "text/plain" });
    fireEvent.change(screen.getByLabelText(/upload ris or csv file/i), {
      target: { files: [file] },
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("File must be .ris or .csv");
  });

  it("ignores a stale response after reviewProjectId changes before it resolves", async () => {
    const first = deferred<Citation[]>();
    const second = deferred<Citation[]>();
    mockedApi.listCitations.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);

    const { rerender } = render(<CitationsPanel reviewProjectId="1" />);
    rerender(<CitationsPanel reviewProjectId="2" />);

    await act(async () => {
      second.resolve([citation("b", "Project B Citation")]);
    });
    expect(await screen.findByText("Project B Citation")).toBeInTheDocument();

    await act(async () => {
      first.resolve([citation("a", "Project A Citation")]);
    });
    expect(screen.queryByText("Project A Citation")).not.toBeInTheDocument();
  });
  describe("when there are no citations", () => {
    it("says so, and points at the upload control", async () => {
      mockedApi.listCitations.mockResolvedValue([]);

      render(<CitationsPanel reviewProjectId="1" />);

      expect(
        await screen.findByText("No citations yet. Upload a RIS or CSV file above.")
      ).toBeInTheDocument();
      expect(screen.queryAllByRole("listitem")).toHaveLength(0);
    });

    it("stays quiet while the list is still loading", async () => {
      const pending = deferred<Citation[]>();
      mockedApi.listCitations.mockReturnValueOnce(pending.promise);

      render(<CitationsPanel reviewProjectId="1" />);

      expect(screen.queryByText(/no citations yet/i)).not.toBeInTheDocument();
      await act(async () => pending.resolve([]));
      expect(await screen.findByText(/no citations yet/i)).toBeInTheDocument();
    });

    it("does not claim the list is empty when it failed to load", async () => {
      mockedApi.listCitations.mockRejectedValueOnce(new Error("down"));

      render(<CitationsPanel reviewProjectId="1" />);

      expect(await screen.findByText(/failed to load citations/i)).toBeInTheDocument();
      expect(screen.queryByText(/no citations yet/i)).not.toBeInTheDocument();
    });

    it("goes away once there is a citation", async () => {
      mockedApi.listCitations.mockResolvedValue([citation("1", "First study")]);

      render(<CitationsPanel reviewProjectId="1" />);

      expect(await screen.findByText("First study")).toBeInTheDocument();
      expect(screen.queryByText(/no citations yet/i)).not.toBeInTheDocument();
    });
  });
});
