import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";

import AccountPage from "./page";

vi.mock("@/lib/api");

const mockedApi = vi.mocked(api);

function stubLocation() {
  Object.defineProperty(window, "location", {
    value: { href: "" },
    writable: true,
    configurable: true,
  });
}

describe("AccountPage", () => {
  beforeEach(() => {
    stubLocation();
  });

  it("shows Billing is not available when billing is disabled", async () => {
    mockedApi.getMySubscription.mockResolvedValue(null);

    render(<AccountPage />);

    expect(await screen.findByText(/billing is not available/i)).toBeInTheDocument();
  });

  it("shows Free plan with an Upgrade action", async () => {
    mockedApi.getMySubscription.mockResolvedValue({ plan: "free", status: null });

    render(<AccountPage />);

    expect(await screen.findByText(/plan: free/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /upgrade/i })).toBeInTheDocument();
  });

  it("shows Paid plan without an Upgrade action", async () => {
    mockedApi.getMySubscription.mockResolvedValue({ plan: "paid", status: "active" });

    render(<AccountPage />);

    expect(await screen.findByText(/plan: paid/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /upgrade/i })).not.toBeInTheDocument();
  });

  it("starts checkout and redirects on Upgrade", async () => {
    mockedApi.getMySubscription.mockResolvedValue({ plan: "free", status: null });
    mockedApi.createCheckoutSession.mockResolvedValue({
      url: "https://stripe.test/checkout/session_123",
    });

    render(<AccountPage />);

    fireEvent.click(await screen.findByRole("button", { name: /upgrade/i }));

    await waitFor(() => expect(mockedApi.createCheckoutSession).toHaveBeenCalled());
    expect(window.location.href).toBe("https://stripe.test/checkout/session_123");
  });

  it("shows an error when checkout fails to start", async () => {
    mockedApi.getMySubscription.mockResolvedValue({ plan: "free", status: null });
    mockedApi.createCheckoutSession.mockRejectedValue(new Error("boom"));

    render(<AccountPage />);

    fireEvent.click(await screen.findByRole("button", { name: /upgrade/i }));

    expect(await screen.findByText(/failed to start checkout/i)).toBeInTheDocument();
  });
});
