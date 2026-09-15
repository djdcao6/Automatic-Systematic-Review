import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";

import AcceptInvitationPage from "./page";

vi.mock("@/lib/api");

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

vi.mock("@/lib/auth", () => ({
  storeToken: vi.fn(),
}));

const mockedApi = vi.mocked(api);

function renderPage(token = "secret-token") {
  return render(<AcceptInvitationPage params={Promise.resolve({ token })} />);
}

describe("AcceptInvitationPage", () => {
  beforeEach(() => {
    mockPush.mockClear();
  });

  it("shows the Review Project name for a pending invitation", async () => {
    mockedApi.getInvitationPublic.mockResolvedValue({
      review_project_name: "My Dual Review",
      status: "pending",
    });

    renderPage();

    expect(await screen.findByText(/my dual review/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /register & join/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /log in & join/i })).toBeInTheDocument();
  });

  it("shows an error for an invalid invitation token", async () => {
    mockedApi.getInvitationPublic.mockRejectedValue(new Error("Invitation not found"));

    renderPage();

    expect(await screen.findByText(/invitation not found/i)).toBeInTheDocument();
  });

  it("shows a message for an already-accepted invitation", async () => {
    mockedApi.getInvitationPublic.mockResolvedValue({
      review_project_name: "My Dual Review",
      status: "accepted",
    });

    renderPage();

    expect(await screen.findByText(/no longer valid/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /register & join/i })).not.toBeInTheDocument();
  });

  it("shows a message for a revoked invitation", async () => {
    mockedApi.getInvitationPublic.mockResolvedValue({
      review_project_name: "My Dual Review",
      status: "revoked",
    });

    renderPage();

    expect(await screen.findByText(/no longer valid/i)).toBeInTheDocument();
  });

  it("registers a new account and joins the project", async () => {
    mockedApi.getInvitationPublic.mockResolvedValue({
      review_project_name: "My Dual Review",
      status: "pending",
    });
    mockedApi.acceptInvitationByRegistering.mockResolvedValue({
      access_token: "new-token",
      token_type: "bearer",
      review_project_id: "project-1",
    });

    renderPage();

    const emailInputs = await screen.findAllByLabelText(/^email$/i);
    const passwordInputs = screen.getAllByLabelText(/^password$/i);
    fireEvent.change(emailInputs[0], { target: { value: "co-reviewer@example.com" } });
    fireEvent.change(passwordInputs[0], { target: { value: "correcthorse" } });
    fireEvent.click(screen.getByRole("button", { name: /register & join/i }));

    await waitFor(() =>
      expect(mockedApi.acceptInvitationByRegistering).toHaveBeenCalledWith("secret-token", {
        email: "co-reviewer@example.com",
        password: "correcthorse",
      })
    );
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/review-projects/project-1"));
  });

  it("shows an error when registration fails", async () => {
    mockedApi.getInvitationPublic.mockResolvedValue({
      review_project_name: "My Dual Review",
      status: "pending",
    });
    mockedApi.acceptInvitationByRegistering.mockRejectedValue(
      new Error("Email is already registered")
    );

    renderPage();

    const emailInputs = await screen.findAllByLabelText(/^email$/i);
    const passwordInputs = screen.getAllByLabelText(/^password$/i);
    fireEvent.change(emailInputs[0], { target: { value: "co-reviewer@example.com" } });
    fireEvent.change(passwordInputs[0], { target: { value: "correcthorse" } });
    fireEvent.click(screen.getByRole("button", { name: /register & join/i }));

    expect(await screen.findByText("Email is already registered")).toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("logs into an existing account and joins the project", async () => {
    mockedApi.getInvitationPublic.mockResolvedValue({
      review_project_name: "My Dual Review",
      status: "pending",
    });
    mockedApi.acceptInvitationByLoggingIn.mockResolvedValue({
      access_token: "existing-token",
      token_type: "bearer",
      review_project_id: "project-1",
    });

    renderPage();

    const emailInputs = await screen.findAllByLabelText(/^email$/i);
    const passwordInputs = screen.getAllByLabelText(/^password$/i);
    fireEvent.change(emailInputs[1], { target: { value: "co-reviewer@example.com" } });
    fireEvent.change(passwordInputs[1], { target: { value: "correcthorse" } });
    fireEvent.click(screen.getByRole("button", { name: /log in & join/i }));

    await waitFor(() =>
      expect(mockedApi.acceptInvitationByLoggingIn).toHaveBeenCalledWith("secret-token", {
        email: "co-reviewer@example.com",
        password: "correcthorse",
      })
    );
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/review-projects/project-1"));
  });

  it("shows an error when login fails", async () => {
    mockedApi.getInvitationPublic.mockResolvedValue({
      review_project_name: "My Dual Review",
      status: "pending",
    });
    mockedApi.acceptInvitationByLoggingIn.mockRejectedValue(
      new Error("Incorrect email or password")
    );

    renderPage();

    const emailInputs = await screen.findAllByLabelText(/^email$/i);
    const passwordInputs = screen.getAllByLabelText(/^password$/i);
    fireEvent.change(emailInputs[1], { target: { value: "co-reviewer@example.com" } });
    fireEvent.change(passwordInputs[1], { target: { value: "wrong" } });
    fireEvent.click(screen.getByRole("button", { name: /log in & join/i }));

    expect(await screen.findByText("Incorrect email or password")).toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
  });
});
