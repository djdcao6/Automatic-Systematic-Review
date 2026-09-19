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

  it("shows a Manage subscription action for a Paid plan", async () => {
    mockedApi.getMySubscription.mockResolvedValue({ plan: "paid", status: "active" });

    render(<AccountPage />);

    expect(
      await screen.findByRole("button", { name: /manage subscription/i })
    ).toBeInTheDocument();
  });

  it("does not show a Manage subscription action for a Free plan", async () => {
    mockedApi.getMySubscription.mockResolvedValue({ plan: "free", status: null });

    render(<AccountPage />);

    await screen.findByRole("button", { name: /upgrade/i });
    expect(
      screen.queryByRole("button", { name: /manage subscription/i })
    ).not.toBeInTheDocument();
  });

  it("opens the Stripe portal on Manage subscription", async () => {
    mockedApi.getMySubscription.mockResolvedValue({ plan: "paid", status: "active" });
    mockedApi.createPortalSession.mockResolvedValue({
      url: "https://stripe.test/portal/session_123",
    });

    render(<AccountPage />);

    fireEvent.click(await screen.findByRole("button", { name: /manage subscription/i }));

    await waitFor(() => expect(mockedApi.createPortalSession).toHaveBeenCalled());
    expect(window.location.href).toBe("https://stripe.test/portal/session_123");
  });

  it("shows an error when the billing portal fails to open", async () => {
    mockedApi.getMySubscription.mockResolvedValue({ plan: "paid", status: "active" });
    mockedApi.createPortalSession.mockRejectedValue(new Error("boom"));

    render(<AccountPage />);

    fireEvent.click(await screen.findByRole("button", { name: /manage subscription/i }));

    expect(await screen.findByText(/failed to open billing portal/i)).toBeInTheDocument();
  });
  describe("before it has anything to show", () => {
    it("keeps the loading message inside the page's main", async () => {
      mockedApi.getMySubscription.mockReturnValueOnce(new Promise(() => {}));

      render(<AccountPage />);
      await vi.waitFor(() => expect(mockedApi.getMySubscription).toHaveBeenCalled());

      expect(screen.getByRole("main")).toHaveTextContent("Loading...");
    });

    it("keeps the billing-unavailable message inside main too", async () => {
      mockedApi.getMySubscription.mockResolvedValueOnce(null);

      render(<AccountPage />);

      const alert = await screen.findByRole("alert");
      expect(alert).toHaveTextContent(/billing is not available/i);
      expect(screen.getByRole("main")).toContainElement(alert);
    });
  });
});
