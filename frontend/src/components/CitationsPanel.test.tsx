import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";

import { CitationsPanel } from "./CitationsPanel";

vi.mock("@/lib/api");

const mockedApi = vi.mocked(api);

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
        source: "PubMed",
        needs_abstract: false,
      },
      {
        id: "2",
        title: "Missing Abstract",
        abstract: null,
        authors: [],
        year: null,
        source: null,
        needs_abstract: true,
      },
    ]);

    render(<CitationsPanel reviewProjectId="1" />);

    expect(await screen.findByText("Has Abstract")).toBeInTheDocument();
    expect(screen.getByText("Missing Abstract")).toBeInTheDocument();
    expect(screen.getByText(/needs abstract/i)).toBeInTheDocument();
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
          source: null,
          needs_abstract: false,
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
});
