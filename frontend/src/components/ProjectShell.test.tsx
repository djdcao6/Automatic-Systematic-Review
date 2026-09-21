import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";
import { useReviewProject } from "@/lib/ReviewProjectContext";

import { ProjectShell } from "./ProjectShell";

vi.mock("@/lib/api");
vi.mock("next/navigation", () => ({
  useSelectedLayoutSegment: () => null,
}));

const mockedApi = vi.mocked(api);

const baseProject = {
  id: "1",
  name: "My Review",
  criteria_locked: false,
  merge_mode: "combine" as const,
  review_mode: "solo" as const,
  owner_reviewer_id: "owner-1",
  co_reviewer_id: null,
  created_at: "2026-01-01T00:00:00Z",
  citations_needing_decision: 3,
  criteria: null,
};

// Stands in for a section page: reads the project through the public hook.
function Probe() {
  const { project, isOwner } = useReviewProject();
  return (
    <p>
      probe: {project.id} {isOwner ? "owner" : "not-owner"}
    </p>
  );
}

// Stands in for a panel that changed something (an upload, a resolved duplicate).
function RefreshButton() {
  const { refreshProject } = useReviewProject();
  return (
    <button type="button" onClick={() => void refreshProject()}>
      Refresh project
    </button>
  );
}

describe("ProjectShell", () => {
  beforeEach(() => {
    mockedApi.getMe.mockResolvedValue({
      id: "owner-1",
      email: "owner@example.com",
      created_at: "2026-01-01T00:00:00Z",
      ai_consent_at: "2026-01-01T00:00:00Z",
    });
    mockedApi.getReviewProject.mockResolvedValue(baseProject);
  });

  it("shows the project header and hands the project to its children", async () => {
    render(
      <ProjectShell reviewProjectId="1">
        <Probe />
      </ProjectShell>
    );

    expect(await screen.findByText("My Review")).toBeInTheDocument();
    expect(screen.getByText(/review mode: solo/i)).toBeInTheDocument();
    expect(screen.getByText("3 citation(s) still need a decision")).toBeInTheDocument();
    expect(screen.getByText("probe: 1 owner")).toBeInTheDocument();
  });

  it("names the project without a heading, so the page's own title is the only h1", async () => {
    render(
      <ProjectShell reviewProjectId="1">
        <main>
          <h1>Criteria</h1>
        </main>
      </ProjectShell>
    );

    expect(await screen.findByText("My Review")).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("updates the header count when a section refreshes the project", async () => {
    mockedApi.getReviewProject
      .mockResolvedValueOnce({ ...baseProject, citations_needing_decision: 3 })
      .mockResolvedValueOnce({ ...baseProject, citations_needing_decision: 2 });

    render(
      <ProjectShell reviewProjectId="1">
        <RefreshButton />
      </ProjectShell>
    );
    expect(await screen.findByText("3 citation(s) still need a decision")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Refresh project" }));

    expect(await screen.findByText("2 citation(s) still need a decision")).toBeInTheDocument();
  });

  it("gives the Owner of a Dual project the Invitations link", async () => {
    mockedApi.getReviewProject.mockResolvedValue({ ...baseProject, review_mode: "dual" });

    render(
      <ProjectShell reviewProjectId="1">
        <Probe />
      </ProjectShell>
    );

    expect(await screen.findByRole("link", { name: "Invitations" })).toHaveAttribute(
      "href",
      "/review-projects/1/invitations"
    );
    expect(screen.getByRole("link", { name: "Conflicts" })).toBeInTheDocument();
  });

  it("hides Invitations from a Co-Reviewer of a Dual project", async () => {
    mockedApi.getReviewProject.mockResolvedValue({ ...baseProject, review_mode: "dual" });
    mockedApi.getMe.mockResolvedValue({
      id: "someone-else",
      email: "co@example.com",
      created_at: "2026-01-01T00:00:00Z",
      ai_consent_at: "2026-01-01T00:00:00Z",
    });

    render(
      <ProjectShell reviewProjectId="1">
        <Probe />
      </ProjectShell>
    );

    expect(await screen.findByRole("link", { name: "Conflicts" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Invitations" })).not.toBeInTheDocument();
  });

  it("shows the error and no rail or header when the project fails to load", async () => {
    mockedApi.getReviewProject.mockRejectedValue(new Error("boom"));

    render(
      <ProjectShell reviewProjectId="1">
        <Probe />
      </ProjectShell>
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Failed to load review project.");
    expect(screen.queryByRole("navigation", { name: "Project" })).not.toBeInTheDocument();
    expect(screen.queryByText("My Review")).not.toBeInTheDocument();
    expect(screen.queryByText(/probe:/)).not.toBeInTheDocument();
  });

  it("waits to show the rail until it knows whether the viewer is the Owner", async () => {
    mockedApi.getReviewProject.mockResolvedValue({ ...baseProject, review_mode: "dual" });
    let resolveMe: (reviewer: api.Reviewer) => void = () => {};
    mockedApi.getMe.mockReturnValue(
      new Promise((resolve) => {
        resolveMe = resolve;
      })
    );

    render(
      <ProjectShell reviewProjectId="1">
        <Probe />
      </ProjectShell>
    );
    await act(async () => {});
    expect(screen.queryByRole("navigation", { name: "Project" })).not.toBeInTheDocument();

    await act(async () => {
      resolveMe({ id: "owner-1", email: "owner@example.com", created_at: "2026-01-01T00:00:00Z", ai_consent_at: "2026-01-01T00:00:00Z" });
    });

    expect(screen.getByRole("link", { name: "Invitations" })).toBeInTheDocument();
  });

  it("still shows the project, without Owner-only links, when the viewer lookup fails", async () => {
    mockedApi.getReviewProject.mockResolvedValue({ ...baseProject, review_mode: "dual" });
    mockedApi.getMe.mockRejectedValue(new Error("no session"));

    render(
      <ProjectShell reviewProjectId="1">
        <Probe />
      </ProjectShell>
    );

    expect(await screen.findByText("probe: 1 not-owner")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Invitations" })).not.toBeInTheDocument();
  });

  describe("an account that pre-dates the AI disclosure", () => {
    const withoutConsent = {
      id: "owner-1",
      email: "owner@example.com",
      created_at: "2026-01-01T00:00:00Z",
      ai_consent_at: null,
    };

    it("is shown the notice instead of the project, so no page can send an AI request first", async () => {
      mockedApi.getMe.mockResolvedValue(withoutConsent);

      render(
        <ProjectShell reviewProjectId="1">
          <Probe />
        </ProjectShell>
      );

      const dialog = await screen.findByRole("dialog", { name: /before you continue/i });
      expect(dialog).toHaveTextContent(/sent to anthropic's api/i);
      expect(dialog).toHaveTextContent(/patient-identifiable data/i);
      expect(screen.queryByText(/probe:/)).not.toBeInTheDocument();
      expect(screen.queryByRole("navigation", { name: "Project" })).not.toBeInTheDocument();
      expect(mockedApi.acceptAiConsent).not.toHaveBeenCalled();
    });

    it("records the agreement and then shows the project", async () => {
      mockedApi.getMe.mockResolvedValue(withoutConsent);
      mockedApi.acceptAiConsent.mockResolvedValue({
        ...withoutConsent,
        ai_consent_at: "2026-09-20T12:00:00Z",
      });
      render(
        <ProjectShell reviewProjectId="1">
          <Probe />
        </ProjectShell>
      );

      fireEvent.click(await screen.findByRole("button", { name: "I understand" }));

      expect(await screen.findByText("probe: 1 owner")).toBeInTheDocument();
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(mockedApi.acceptAiConsent).toHaveBeenCalledTimes(1);
    });

    it("keeps the project hidden and says so when the agreement cannot be recorded", async () => {
      mockedApi.getMe.mockResolvedValue(withoutConsent);
      mockedApi.acceptAiConsent.mockRejectedValue(new Error("Failed to record your agreement"));
      render(
        <ProjectShell reviewProjectId="1">
          <Probe />
        </ProjectShell>
      );

      fireEvent.click(await screen.findByRole("button", { name: "I understand" }));

      expect(await screen.findByRole("alert")).toHaveTextContent("Failed to record your agreement");
      expect(screen.getByRole("dialog")).toBeInTheDocument();
      expect(screen.queryByText(/probe:/)).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "I understand" })).toBeEnabled();
    });

    it("can try again after a failure", async () => {
      mockedApi.getMe.mockResolvedValue(withoutConsent);
      mockedApi.acceptAiConsent
        .mockRejectedValueOnce(new Error("Failed to record your agreement"))
        .mockResolvedValueOnce({ ...withoutConsent, ai_consent_at: "2026-09-20T12:00:00Z" });
      render(
        <ProjectShell reviewProjectId="1">
          <Probe />
        </ProjectShell>
      );
      fireEvent.click(await screen.findByRole("button", { name: "I understand" }));
      await screen.findByRole("alert");

      fireEvent.click(screen.getByRole("button", { name: "I understand" }));

      expect(await screen.findByText("probe: 1 owner")).toBeInTheDocument();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
  });

  it("does not show the notice to an account that already agreed", async () => {
    render(
      <ProjectShell reviewProjectId="1">
        <Probe />
      </ProjectShell>
    );

    expect(await screen.findByText("probe: 1 owner")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("never shows the previous project while a different one loads", async () => {
    let resolveOther: (project: api.ReviewProjectDetail) => void = () => {};
    mockedApi.getReviewProject.mockImplementation((id) =>
      id === "1"
        ? Promise.resolve(baseProject)
        : new Promise((resolve) => {
            resolveOther = resolve;
          })
    );
    const { rerender } = render(
      <ProjectShell reviewProjectId="1">
        <Probe />
      </ProjectShell>
    );
    await screen.findByText("My Review");

    rerender(
      <ProjectShell reviewProjectId="2">
        <Probe />
      </ProjectShell>
    );
    expect(screen.queryByText("My Review")).not.toBeInTheDocument();
    // The children unmount too, not just the header. A list panel keeps its rows
    // in its own state, so this is what stops it showing the previous project's.
    expect(screen.queryByText("probe: 1 owner")).not.toBeInTheDocument();

    await act(async () => {
      resolveOther({ ...baseProject, id: "2", name: "Other Review" });
    });
    expect(screen.getByText("Other Review")).toBeInTheDocument();
  });

  it("ignores a slow response for a project the Reviewer has already left", async () => {
    let resolveFirst: (project: api.ReviewProjectDetail) => void = () => {};
    mockedApi.getReviewProject.mockImplementation((id) =>
      id === "1"
        ? new Promise((resolve) => {
            resolveFirst = resolve;
          })
        : Promise.resolve({ ...baseProject, id: "2", name: "Other Review" })
    );
    const { rerender } = render(
      <ProjectShell reviewProjectId="1">
        <Probe />
      </ProjectShell>
    );
    rerender(
      <ProjectShell reviewProjectId="2">
        <Probe />
      </ProjectShell>
    );
    await screen.findByText("Other Review");

    await act(async () => {
      resolveFirst(baseProject);
    });

    expect(screen.getByText("Other Review")).toBeInTheDocument();
  });

  it("keeps the current project and shows no error when a refresh fails", async () => {
    mockedApi.getReviewProject
      .mockResolvedValueOnce({ ...baseProject, citations_needing_decision: 3 })
      .mockRejectedValueOnce(new Error("network"));
    render(
      <ProjectShell reviewProjectId="1">
        <RefreshButton />
      </ProjectShell>
    );
    await screen.findByText("3 citation(s) still need a decision");

    fireEvent.click(screen.getByRole("button", { name: "Refresh project" }));
    await act(async () => {});

    expect(screen.getByText("3 citation(s) still need a decision")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("exports the project as a CSV file using the server-provided filename", async () => {
    mockedApi.exportReviewProject.mockResolvedValue({
      blob: new Blob(["title\n"], { type: "text/csv" }),
      filename: "my-review-a1b2c3d4.csv",
    });
    const createObjectURL = vi.fn().mockReturnValue("blob:mock-url");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL });
    const appendChildSpy = vi.spyOn(document.body, "appendChild");
    render(
      <ProjectShell reviewProjectId="1">
        <Probe />
      </ProjectShell>
    );

    fireEvent.click(await screen.findByRole("button", { name: /export csv/i }));

    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock-url"));
    const link = appendChildSpy.mock.calls
      .map((call) => call[0])
      .find((node): node is HTMLAnchorElement => node instanceof HTMLAnchorElement);
    expect(link?.download).toBe("my-review-a1b2c3d4.csv");

    appendChildSpy.mockRestore();
    vi.unstubAllGlobals();
  });

  it("shows an alert when the export fails", async () => {
    mockedApi.exportReviewProject.mockRejectedValue(new Error("boom"));
    render(
      <ProjectShell reviewProjectId="1">
        <Probe />
      </ProjectShell>
    );

    fireEvent.click(await screen.findByRole("button", { name: /export csv/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/failed to export/i);
  });

  it("loads the project and the viewer once, however many sections the Reviewer visits", async () => {
    const { rerender } = render(
      <ProjectShell reviewProjectId="1">
        <main>Criteria page</main>
      </ProjectShell>
    );
    await screen.findByText("Criteria page");

    rerender(
      <ProjectShell reviewProjectId="1">
        <main>Citations page</main>
      </ProjectShell>
    );
    expect(screen.getByText("Citations page")).toBeInTheDocument();

    expect(mockedApi.getReviewProject).toHaveBeenCalledTimes(1);
    expect(mockedApi.getMe).toHaveBeenCalledTimes(1);
  });

  it("leaves the main landmark to the page it wraps", async () => {
    render(
      <ProjectShell reviewProjectId="1">
        <main>Criteria page</main>
      </ProjectShell>
    );

    await screen.findByText("Criteria page");
    expect(screen.getAllByRole("main")).toHaveLength(1);
  });
});
