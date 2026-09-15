import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";
import * as auth from "@/lib/auth";

import LoginPage from "./page";

vi.mock("@/lib/api");
vi.mock("@/lib/auth");

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

const mockedApi = vi.mocked(api);
const mockedAuth = vi.mocked(auth);

describe("LoginPage", () => {
  beforeEach(() => {
    mockPush.mockClear();
    mockedApi.loginReviewer.mockResolvedValue({
      access_token: "a-jwt-token",
      token_type: "bearer",
    });
  });

  it("logs in, stores the token, and redirects home", async () => {
    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "reviewer@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: "correcthorse" },
    });
    fireEvent.click(screen.getByRole("button", { name: /log in/i }));

    await waitFor(() =>
      expect(mockedApi.loginReviewer).toHaveBeenCalledWith({
        email: "reviewer@example.com",
        password: "correcthorse",
      })
    );
    expect(mockedAuth.storeToken).toHaveBeenCalledWith("a-jwt-token");
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/"));
  });

  it("shows an error when login fails without storing a token", async () => {
    mockedApi.loginReviewer.mockRejectedValue(
      new Error("Incorrect email or password")
    );

    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: "reviewer@example.com" },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: "wrong-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: /log in/i }));

    expect(
      await screen.findByText("Incorrect email or password")
    ).toBeInTheDocument();
    expect(mockedAuth.storeToken).not.toHaveBeenCalled();
    expect(mockPush).not.toHaveBeenCalled();
  });
});
