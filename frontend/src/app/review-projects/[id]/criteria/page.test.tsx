import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ProjectShell } from "@/components/ProjectShell";
import * as api from "@/lib/api";
import { baseProject, renderWithProject } from "@/test/renderWithProject";

import CriteriaPage from "./page";

vi.mock("@/lib/api");
vi.mock("next/navigation", () => ({
  useSelectedLayoutSegment: () => "criteria",
}));

const mockedApi = vi.mocked(api);

describe("CriteriaPage", () => {
  it("shows previously saved criteria", () => {
    renderWithProject(<CriteriaPage />, {
      project: {
        criteria: {
          population: "Adults with diabetes",
          intervention: "Metformin",
          comparison: "Placebo",
          outcome: "HbA1c",
          exclusion_rules: ["Non-English"],
          notes: "Exclude conference abstracts.",
        },
      },
    });

    expect(screen.getByDisplayValue("Adults with diabetes")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Metformin")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Placebo")).toBeInTheDocument();
    expect(screen.getByDisplayValue("HbA1c")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Non-English")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Exclude conference abstracts.")).toBeInTheDocument();
  });

  it("renders blank fields when no criteria exists yet", () => {
    renderWithProject(<CriteriaPage />);

    expect(screen.getByLabelText(/population/i)).toHaveValue("");
  });

  it("saves criteria with blank PICO fields and exclusion rules", async () => {
    mockedApi.saveCriteria.mockResolvedValue({
      population: null,
      intervention: null,
      comparison: null,
      outcome: null,
      exclusion_rules: ["Non-English", "Case reports"],
      notes: "Adult populations only.",
    });
    renderWithProject(<CriteriaPage />);

    fireEvent.change(screen.getByLabelText(/exclusion rules/i), {
      target: { value: "Non-English\nCase reports" },
    });
    fireEvent.change(screen.getByLabelText(/notes/i), {
      target: { value: "Adult populations only." },
    });
    fireEvent.click(screen.getByRole("button", { name: /save criteria/i }));

    await waitFor(() =>
      expect(mockedApi.saveCriteria).toHaveBeenCalledWith("1", {
        population: null,
        intervention: null,
        comparison: null,
        outcome: null,
        exclusion_rules: ["Non-English", "Case reports"],
        notes: "Adult populations only.",
      })
    );
  });

  it("tells the Reviewer when saving fails", async () => {
    mockedApi.saveCriteria.mockRejectedValue(new Error("boom"));
    renderWithProject(<CriteriaPage />);

    fireEvent.click(screen.getByRole("button", { name: /save criteria/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Failed to save criteria.");
  });

  it("shows the saved criteria again after the Reviewer leaves and comes back", async () => {
    const saved = {
      population: "Adults",
      intervention: null,
      comparison: null,
      outcome: null,
      exclusion_rules: [],
      notes: null,
    };
    mockedApi.getMe.mockResolvedValue({
      id: "owner-1",
      email: "owner@example.com",
      created_at: "2026-01-01T00:00:00Z",
    });
    mockedApi.getReviewProject
      .mockResolvedValueOnce(baseProject)
      .mockResolvedValue({ ...baseProject, criteria: saved });
    mockedApi.saveCriteria.mockResolvedValue(saved);
    const { rerender } = render(
      <ProjectShell reviewProjectId="1">
        <CriteriaPage />
      </ProjectShell>
    );
    fireEvent.change(await screen.findByLabelText("Population"), { target: { value: "Adults" } });
    fireEvent.click(screen.getByRole("button", { name: /save criteria/i }));
    await waitFor(() => expect(mockedApi.saveCriteria).toHaveBeenCalled());
    await act(async () => {});

    rerender(
      <ProjectShell reviewProjectId="1">
        <main>Another section</main>
      </ProjectShell>
    );
    rerender(
      <ProjectShell reviewProjectId="1">
        <CriteriaPage />
      </ProjectShell>
    );

    expect(screen.getByLabelText("Population")).toHaveValue("Adults");
  });
});
