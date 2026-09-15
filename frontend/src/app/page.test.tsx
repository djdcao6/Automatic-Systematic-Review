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
      merge_mode: "combine",
      review_mode: "solo",
      owner_reviewer_id: "owner-1",
      co_reviewer_id: null,
      created_at: "2026-01-01T00:00:00Z",
    });
  });

  it("lists existing review projects", async () => {
    mockedApi.listReviewProjects.mockResolvedValue([
      {
        id: "1",
        name: "Existing Review",
        criteria_locked: false,
        merge_mode: "combine",
        review_mode: "solo",
        owner_reviewer_id: "owner-1",
        co_reviewer_id: null,
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
    fireEvent.change(screen.getByLabelText(/merge mode/i), {
      target: { value: "combine" },
    });
    fireEvent.change(screen.getByLabelText(/review mode/i), {
      target: { value: "solo" },
    });
    fireEvent.click(screen.getByRole("button", { name: /create review project/i }));

    expect(await screen.findByText("New Review")).toBeInTheDocument();
    expect(mockedApi.createReviewProject).toHaveBeenCalledWith({
      name: "New Review",
      merge_mode: "combine",
      review_mode: "solo",
    });
  });

  it("does not submit without a merge mode chosen", async () => {
    render(<Home />);

    await waitFor(() => expect(mockedApi.listReviewProjects).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText(/project name/i), {
      target: { value: "New Review" },
    });
    fireEvent.change(screen.getByLabelText(/review mode/i), {
      target: { value: "solo" },
    });
    fireEvent.click(screen.getByRole("button", { name: /create review project/i }));

    await waitFor(() => expect(mockedApi.createReviewProject).not.toHaveBeenCalled());
  });

  it("does not submit without a review mode chosen", async () => {
    render(<Home />);

    await waitFor(() => expect(mockedApi.listReviewProjects).toHaveBeenCalled());

    fireEvent.change(screen.getByLabelText(/project name/i), {
      target: { value: "New Review" },
    });
    fireEvent.change(screen.getByLabelText(/merge mode/i), {
      target: { value: "combine" },
    });
    fireEvent.click(screen.getByRole("button", { name: /create review project/i }));

    await waitFor(() => expect(mockedApi.createReviewProject).not.toHaveBeenCalled());
  });
});
