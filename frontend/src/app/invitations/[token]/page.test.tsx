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
    fireEvent.click(screen.getByLabelText(/i understand/i));
    fireEvent.click(screen.getByRole("button", { name: /register & join/i }));

    await waitFor(() =>
      expect(mockedApi.acceptInvitationByRegistering).toHaveBeenCalledWith("secret-token", {
        email: "co-reviewer@example.com",
        password: "correcthorse",
        ai_consent: true,
      })
    );
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/review-projects/project-1"));
  });

  it("asks the new Reviewer to accept the AI disclosure, with the notice beside the box", async () => {
    mockedApi.getInvitationPublic.mockResolvedValue({
      review_project_name: "My Dual Review",
      status: "pending",
    });

    renderPage();

    const checkbox = await screen.findByRole("checkbox", { name: /anthropic's api/i });
    expect(checkbox).not.toBeChecked();
    expect(checkbox).toHaveAccessibleName(/patient-identifiable data/i);
    // Only the Register form has it: an existing account already agreed when it signed up.
    expect(screen.getAllByRole("checkbox")).toHaveLength(1);
  });

  it("does not register until the AI disclosure is accepted", async () => {
    mockedApi.getInvitationPublic.mockResolvedValue({
      review_project_name: "My Dual Review",
      status: "pending",
    });

    renderPage();

    const emailInputs = await screen.findAllByLabelText(/^email$/i);
    const passwordInputs = screen.getAllByLabelText(/^password$/i);
    fireEvent.change(emailInputs[0], { target: { value: "co-reviewer@example.com" } });
    fireEvent.change(passwordInputs[0], { target: { value: "correcthorse" } });
    fireEvent.click(screen.getByRole("button", { name: /register & join/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/accept the ai disclosure/i);
    expect(mockedApi.acceptInvitationByRegistering).not.toHaveBeenCalled();
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("does not register after the AI disclosure is accepted and then withdrawn", async () => {
    mockedApi.getInvitationPublic.mockResolvedValue({
      review_project_name: "My Dual Review",
      status: "pending",
    });

    renderPage();

    const checkbox = await screen.findByLabelText(/i understand/i);
    fireEvent.click(checkbox);
    fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole("button", { name: /register & join/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/accept the ai disclosure/i);
    expect(mockedApi.acceptInvitationByRegistering).not.toHaveBeenCalled();
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
    fireEvent.click(screen.getByLabelText(/i understand/i));
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
