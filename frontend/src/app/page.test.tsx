import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";

import Home from "./page";

vi.mock("@/lib/api");

const mockedApi = vi.mocked(api);

describe("Home", () => {
  beforeEach(() => {
    mockedApi.listReviewProjects.mockResolvedValue([]);
    mockedApi.createReviewProject.mockResolvedValue({
      id: "1",
      name: "New Review",
      criteria_locked: false,
      created_at: "2026-01-01T00:00:00Z",
    });
  });

  it("lists existing review projects", async () => {
    mockedApi.listReviewProjects.mockResolvedValue([
      {
        id: "1",
        name: "Existing Review",
        criteria_locked: false,
        created_at: "2026-01-01T00:00:00Z",
      },
    ]);

    render(<Home />);

    expect(await screen.findByText("Existing Review")).toBeInTheDocument();
  });

  it("creates a review project and shows it in the list", async () => {
    render(<Home />);

    await waitFor(() => expect(mockedApi.listReviewProjects).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText(/project name/i), {
      target: { value: "New Review" },
    });
    fireEvent.click(screen.getByRole("button", { name: /create review project/i }));

    expect(await screen.findByText("New Review")).toBeInTheDocument();
    expect(mockedApi.createReviewProject).toHaveBeenCalledWith("New Review");
  });
});
