import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";

import RegisterPage from "./page";

vi.mock("@/lib/api");

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

const mockedApi = vi.mocked(api);

function fillCredentials() {
  fireEvent.change(screen.getByLabelText(/email/i), {
    target: { value: "reviewer@example.com" },
  });
  fireEvent.change(screen.getByLabelText(/password/i), {
    target: { value: "correcthorse" },
  });
}

describe("RegisterPage", () => {
  beforeEach(() => {
    mockPush.mockClear();
    mockedApi.registerReviewer.mockReset();
    mockedApi.registerReviewer.mockResolvedValue({
      id: "1",
      email: "reviewer@example.com",
      created_at: "2026-01-01T00:00:00Z",
      ai_consent_at: "2026-01-01T00:00:00Z",
    });
  });

  it("registers a reviewer and redirects to login", async () => {
    render(<RegisterPage />);

    fillCredentials();
    fireEvent.click(screen.getByLabelText(/i understand/i));
    fireEvent.click(screen.getByRole("button", { name: /register/i }));

    await waitFor(() =>
      expect(mockedApi.registerReviewer).toHaveBeenCalledWith({
        email: "reviewer@example.com",
        password: "correcthorse",
        ai_consent: true,
      })
    );
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/login"));
  });

  it("asks the Reviewer to accept the AI disclosure, with the notice beside the box", () => {
    render(<RegisterPage />);

    const checkbox = screen.getByRole("checkbox", { name: /anthropic's api/i });

    expect(checkbox).not.toBeChecked();
    expect(checkbox).toHaveAccessibleName(/patient-identifiable data/i);
  });

  it("does not register until the AI disclosure is accepted", async () => {
    render(<RegisterPage />);

    fillCredentials();
    fireEvent.click(screen.getByRole("button", { name: /register/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/accept the ai disclosure/i);
    expect(mockedApi.registerReviewer).not.toHaveBeenCalled();
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("does not register after the AI disclosure is accepted and then withdrawn", async () => {
    render(<RegisterPage />);

    fillCredentials();
    const checkbox = screen.getByLabelText(/i understand/i);
    fireEvent.click(checkbox);
    fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole("button", { name: /register/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/accept the ai disclosure/i);
    expect(mockedApi.registerReviewer).not.toHaveBeenCalled();
  });

  it("clears the reminder once registration is tried again with the box ticked", async () => {
    render(<RegisterPage />);
    fillCredentials();
    fireEvent.click(screen.getByRole("button", { name: /register/i }));
    await screen.findByRole("alert");

    fireEvent.click(screen.getByLabelText(/i understand/i));
    fireEvent.click(screen.getByRole("button", { name: /register/i }));

    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/login"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows an error when registration fails", async () => {
    mockedApi.registerReviewer.mockRejectedValue(
      new Error("Email is already registered")
    );

    render(<RegisterPage />);

    fillCredentials();
    fireEvent.click(screen.getByLabelText(/i understand/i));
    fireEvent.click(screen.getByRole("button", { name: /register/i }));

    expect(
      await screen.findByText("Email is already registered")
    ).toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
  });
});
