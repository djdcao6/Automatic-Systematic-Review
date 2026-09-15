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

describe("RegisterPage", () => {
  beforeEach(() => {
    mockPush.mockClear();
    mockedApi.registerReviewer.mockResolvedValue({
      id: "1",
      email: "reviewer@example.com",
      created_at: "2026-01-01T00:00:00Z",
    });
  });

  it("registers a reviewer and redirects to login", async () => {
    render(<RegisterPage />);

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "reviewer@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: "correcthorse" },
    });
    fireEvent.click(screen.getByRole("button", { name: /register/i }));

    await waitFor(() =>
      expect(mockedApi.registerReviewer).toHaveBeenCalledWith({
        email: "reviewer@example.com",
        password: "correcthorse",
      })
    );
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/login"));
  });

  it("shows an error when registration fails", async () => {
    mockedApi.registerReviewer.mockRejectedValue(
      new Error("Email is already registered")
    );

    render(<RegisterPage />);

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "reviewer@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: "correcthorse" },
    });
    fireEvent.click(screen.getByRole("button", { name: /register/i }));

    expect(
      await screen.findByText("Email is already registered")
    ).toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
  });
});
