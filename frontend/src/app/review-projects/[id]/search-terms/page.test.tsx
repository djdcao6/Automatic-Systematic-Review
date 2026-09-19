import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";
import { renderWithProject } from "@/test/renderWithProject";

import SearchTermsPage from "./page";

vi.mock("@/lib/api");

const mockedApi = vi.mocked(api);

describe("SearchTermsPage", () => {
  it("shows the Search Terms section for the project", async () => {
    mockedApi.getSearchTerms.mockResolvedValue(null);
    renderWithProject(<SearchTermsPage />);

    expect(await screen.findByRole("heading", { name: "Search Terms" })).toBeInTheDocument();
    expect(mockedApi.getSearchTerms).toHaveBeenCalledWith("1");
  });
});
