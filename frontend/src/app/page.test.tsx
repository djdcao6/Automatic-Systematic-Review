import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";
import { ReviewProjectCapError } from "@/lib/api";

import Home from "./page";

// Automocking would also replace ReviewProjectCapError's constructor, so a
// mock-thrown instance would lose its message (#41's tests construct one
// directly to simulate the API layer's rejection) — keep the real class,
// mock only the functions.
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    listReviewProjects: vi.fn(),
    createReviewProject: vi.fn(),
    getMySubscription: vi.fn(),
  };
});

const mockedApi = vi.mocked(api);

describe("Home", () => {
  beforeEach(() => {
    mockedApi.listReviewProjects.mockResolvedValue([]);
    mockedApi.getMySubscription.mockResolvedValue(null);
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

  it("hides the Account/Billing link while billing is disabled", async () => {
    render(<Home />);

    await waitFor(() => expect(mockedApi.getMySubscription).toHaveBeenCalled());
    expect(screen.queryByRole("link", { name: /account.*billing/i })).not.toBeInTheDocument();
  });

  it("shows the Account/Billing link once billing is enabled", async () => {
    mockedApi.getMySubscription.mockResolvedValue({ plan: "free", status: null });

    render(<Home />);

    expect(await screen.findByRole("link", { name: /account.*billing/i })).toHaveAttribute(
      "href",
      "/account"
    );
  });

  it("shows the cap error message with a link to Account/Billing when blocked", async () => {
    mockedApi.getMySubscription.mockResolvedValue({ plan: "free", status: null });
    mockedApi.createReviewProject.mockRejectedValue(
      new ReviewProjectCapError(
        "Free Plan is limited to 1 Review Project. Upgrade on the Account/Billing page to create more."
      )
    );

    render(<Home />);

    await waitFor(() => expect(mockedApi.listReviewProjects).toHaveBeenCalled());
    fireEvent.change(screen.getByLabelText(/project name/i), {
      target: { value: "Second Review" },
    });
    fireEvent.change(screen.getByLabelText(/merge mode/i), {
      target: { value: "combine" },
    });
    fireEvent.change(screen.getByLabelText(/review mode/i), {
      target: { value: "solo" },
    });
    fireEvent.click(screen.getByRole("button", { name: /create review project/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/free plan is limited to 1 review project/i);
    expect(within(alert).getByRole("link", { name: /account.*billing/i })).toHaveAttribute(
      "href",
      "/account"
    );
  });

  it("shows the 403 message with no Account/Billing link while billing is off", async () => {
    // The invite-only restriction (#60) also arrives as a 403 while billing is
    // off, and the billing page is hidden then.
    mockedApi.createReviewProject.mockRejectedValue(
      new ReviewProjectCapError(
        "Your account can work in the Review Project that invited you, but creating Review Projects is invite only during the pilot."
      )
    );

    render(<Home />);

    await waitFor(() => expect(mockedApi.getMySubscription).toHaveBeenCalled());
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

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/invite only during the pilot/i);
    expect(within(alert).queryByRole("link")).not.toBeInTheDocument();
  });

  it("shows a generic error, with no Account/Billing link, for a non-cap failure", async () => {
    mockedApi.createReviewProject.mockRejectedValue(new Error("boom"));

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

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/failed to create review project/i);
    expect(within(alert).queryByRole("link")).not.toBeInTheDocument();
  });
  describe("when there are no review projects", () => {
    it("says so, and points at the form above", async () => {
      mockedApi.listReviewProjects.mockResolvedValue([]);

      render(<Home />);

      expect(
        await screen.findByText("No review projects yet. Create one above.")
      ).toBeInTheDocument();
    });

    it("stays quiet while the projects are still loading", async () => {
      let resolve!: (projects: []) => void;
      mockedApi.listReviewProjects.mockReturnValueOnce(
        new Promise((res) => {
          resolve = res;
        })
      );

      render(<Home />);

      expect(screen.queryByText(/no review projects yet/i)).not.toBeInTheDocument();
      resolve([]);
      expect(await screen.findByText(/no review projects yet/i)).toBeInTheDocument();
    });

    it("does not claim there are none when the projects failed to load", async () => {
      mockedApi.listReviewProjects.mockRejectedValueOnce(new Error("down"));

      render(<Home />);

      expect(await screen.findByText(/failed to load review projects/i)).toBeInTheDocument();
      expect(screen.queryByText(/no review projects yet/i)).not.toBeInTheDocument();
    });

    it("goes away as soon as a project is created", async () => {
      mockedApi.listReviewProjects.mockResolvedValue([]);
      render(<Home />);
      await screen.findByText(/no review projects yet/i);

      fireEvent.change(screen.getByLabelText("Project name"), { target: { value: "New Review" } });
      fireEvent.change(screen.getByLabelText("Merge Mode"), { target: { value: "combine" } });
      fireEvent.change(screen.getByLabelText("Review Mode"), { target: { value: "solo" } });
      fireEvent.click(screen.getByRole("button", { name: /create review project/i }));

      expect(await screen.findByRole("link", { name: "New Review" })).toBeInTheDocument();
      expect(screen.queryByText(/no review projects yet/i)).not.toBeInTheDocument();
    });
  });
});
