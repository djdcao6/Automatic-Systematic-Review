import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";
import { renderWithProject } from "@/test/renderWithProject";

import ExtractionFieldsPage from "./page";

vi.mock("@/lib/api");

const mockedApi = vi.mocked(api);

describe("ExtractionFieldsPage", () => {
  it("shows the Extraction Fields section for the project", async () => {
    mockedApi.listExtractionFields.mockResolvedValue([]);
    renderWithProject(<ExtractionFieldsPage />);

    expect(await screen.findByRole("heading", { name: "Extraction Fields" })).toBeInTheDocument();
    expect(mockedApi.listExtractionFields).toHaveBeenCalledWith("1");
  });
});
