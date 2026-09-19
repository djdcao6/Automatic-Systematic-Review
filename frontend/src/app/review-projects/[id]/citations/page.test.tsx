import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";
import { renderWithProject } from "@/test/renderWithProject";

import CitationsPage from "./page";

vi.mock("@/lib/api");

const mockedApi = vi.mocked(api);

describe("CitationsPage", () => {
  it("lists the project's citations", async () => {
    mockedApi.listCitations.mockResolvedValue([
      {
        id: "c1",
        title: "A trial of metformin",
        abstract: "Abstract",
        authors: [],
        year: 2022,
        source: [],
        needs_abstract: false,
        blocked_pending_co_reviewer: false,
      },
    ]);
    renderWithProject(<CitationsPage />);

    expect(await screen.findByRole("link", { name: "A trial of metformin" })).toHaveAttribute(
      "href",
      "/review-projects/1/citations/c1"
    );
    expect(mockedApi.listCitations).toHaveBeenCalledWith("1");
  });

  it("refreshes the project after citations are uploaded", async () => {
    mockedApi.listCitations.mockResolvedValue([]);
    mockedApi.uploadCitations.mockResolvedValue({ created: 1, skipped: [] });
    const { refreshProject } = renderWithProject(<CitationsPage />);
    await screen.findByText(/no citations yet/i);

    const file = new File(["title\nA\n"], "citations.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText(/upload ris or csv file/i), {
      target: { files: [file] },
    });

    await waitFor(() => expect(refreshProject).toHaveBeenCalledTimes(1));
  });
});
