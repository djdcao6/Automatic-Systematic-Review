import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as auth from "@/lib/auth";

import { LogoutButton } from "./LogoutButton";

vi.mock("@/lib/auth");

const mockPush = vi.fn();
let mockPathname = "/";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  usePathname: () => mockPathname,
}));

const mockedAuth = vi.mocked(auth);

// Regression: ISSUE-005 — no page offered a way to log out, so a Reviewer on a
// shared machine couldn't end their session from the UI.
// Found by /qa on 2026-09-19
// Report: .gstack/qa-reports/qa-report-localhost-2026-09-19.md
describe("LogoutButton", () => {
  beforeEach(() => {
    mockPush.mockClear();
    mockPathname = "/";
    mockedAuth.getToken.mockReturnValue("a-jwt-token");
    // The real clearToken removes the stored token; mirror that.
    mockedAuth.clearToken.mockImplementation(() => {
      mockedAuth.getToken.mockReturnValue(null);
    });
  });

  it("offers Log out while a token is stored", () => {
    render(<LogoutButton />);

    expect(screen.getByRole("button", { name: /log out/i })).toBeInTheDocument();
  });

  it("renders nothing when nobody is logged in", () => {
    mockedAuth.getToken.mockReturnValue(null);

    render(<LogoutButton />);

    expect(screen.queryByRole("button", { name: /log out/i })).not.toBeInTheDocument();
  });

  it("clears the token, hides itself, and sends the Reviewer to /login on click", () => {
    render(<LogoutButton />);

    fireEvent.click(screen.getByRole("button", { name: /log out/i }));

    expect(mockedAuth.clearToken).toHaveBeenCalledTimes(1);
    expect(mockPush).toHaveBeenCalledWith("/login");
    expect(screen.queryByRole("button", { name: /log out/i })).not.toBeInTheDocument();
  });

  it("hides itself even when the Reviewer is already on /login", () => {
    // pathname doesn't change on push("/login") here, so hiding can't rely on it.
    mockPathname = "/login";
    render(<LogoutButton />);

    fireEvent.click(screen.getByRole("button", { name: /log out/i }));

    expect(screen.queryByRole("button", { name: /log out/i })).not.toBeInTheDocument();
  });

  it("hides itself when another tab logs out (storage event)", () => {
    render(<LogoutButton />);
    expect(screen.getByRole("button", { name: /log out/i })).toBeInTheDocument();

    act(() => {
      mockedAuth.getToken.mockReturnValue(null);
      window.dispatchEvent(new Event("storage"));
    });

    expect(screen.queryByRole("button", { name: /log out/i })).not.toBeInTheDocument();
  });

  it("appears after a login navigates on from a page rendered without a token", () => {
    // The root layout never remounts, so logging in (store token, push "/")
    // must be picked up on the next navigation rather than only on first load.
    mockPathname = "/login";
    mockedAuth.getToken.mockReturnValue(null);
    const { rerender } = render(<LogoutButton />);
    expect(screen.queryByRole("button", { name: /log out/i })).not.toBeInTheDocument();

    mockedAuth.getToken.mockReturnValue("a-jwt-token");
    mockPathname = "/";
    rerender(<LogoutButton />);

    expect(screen.getByRole("button", { name: /log out/i })).toBeInTheDocument();
  });

  it("disappears when a navigation finds the token gone (e.g. expired session)", () => {
    const { rerender } = render(<LogoutButton />);
    expect(screen.getByRole("button", { name: /log out/i })).toBeInTheDocument();

    mockedAuth.getToken.mockReturnValue(null);
    mockPathname = "/login";
    rerender(<LogoutButton />);

    expect(screen.queryByRole("button", { name: /log out/i })).not.toBeInTheDocument();
  });
});
