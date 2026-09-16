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
});
