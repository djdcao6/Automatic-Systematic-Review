import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";

import { ExtractionFieldsPanel } from "./ExtractionFieldsPanel";

vi.mock("@/lib/api");

const mockedApi = vi.mocked(api);

const sampleSizeField = {
  id: "f1",
  name: "Sample size",
  description: "Number of participants",
  archived: false,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

describe("ExtractionFieldsPanel", () => {
  beforeEach(() => {
    mockedApi.listExtractionFields.mockResolvedValue([]);
  });

  it("lists active extraction fields", async () => {
    mockedApi.listExtractionFields.mockResolvedValue([sampleSizeField]);

    render(<ExtractionFieldsPanel reviewProjectId="1" />);

    expect(await screen.findByText("Sample size")).toBeInTheDocument();
    expect(screen.getByText("Number of participants")).toBeInTheDocument();
  });

  it("adds a new extraction field and refreshes the list", async () => {
    mockedApi.listExtractionFields
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([sampleSizeField]);
    mockedApi.createExtractionField.mockResolvedValue(sampleSizeField);

    render(<ExtractionFieldsPanel reviewProjectId="1" />);

    await waitFor(() => expect(mockedApi.listExtractionFields).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText(/^name$/i), {
      target: { value: "Sample size" },
    });
    fireEvent.change(screen.getByLabelText(/^description$/i), {
      target: { value: "Number of participants" },
    });
    fireEvent.click(screen.getByRole("button", { name: /add field/i }));

    await waitFor(() =>
      expect(mockedApi.createExtractionField).toHaveBeenCalledWith("1", {
        name: "Sample size",
        description: "Number of participants",
      })
    );
    expect(await screen.findByText("Sample size")).toBeInTheDocument();
  });

  it("clears the add-field form after a successful submit", async () => {
    mockedApi.listExtractionFields
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([sampleSizeField]);
    mockedApi.createExtractionField.mockResolvedValue(sampleSizeField);

    render(<ExtractionFieldsPanel reviewProjectId="1" />);

    await waitFor(() => expect(mockedApi.listExtractionFields).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText(/^name$/i), {
      target: { value: "Sample size" },
    });
    fireEvent.click(screen.getByRole("button", { name: /add field/i }));

    await waitFor(() => expect(mockedApi.createExtractionField).toHaveBeenCalled());
    expect(screen.getByLabelText(/^name$/i)).toHaveValue("");
  });

  it("shows an error when adding a field fails", async () => {
    mockedApi.createExtractionField.mockRejectedValue(new Error("boom"));

    render(<ExtractionFieldsPanel reviewProjectId="1" />);

    await waitFor(() => expect(mockedApi.listExtractionFields).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText(/^name$/i), {
      target: { value: "Sample size" },
    });
    fireEvent.click(screen.getByRole("button", { name: /add field/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/failed to (add|create)/i);
  });

  it("edits a field's name and description", async () => {
    mockedApi.listExtractionFields
      .mockResolvedValueOnce([sampleSizeField])
      .mockResolvedValueOnce([
        { ...sampleSizeField, name: "Sample size (n)", description: "Total enrolled" },
      ]);
    mockedApi.updateExtractionField.mockResolvedValue({
      ...sampleSizeField,
      name: "Sample size (n)",
      description: "Total enrolled",
    });

    render(<ExtractionFieldsPanel reviewProjectId="1" />);

    fireEvent.click(await screen.findByRole("button", { name: /edit/i }));

    const nameInput = screen.getByDisplayValue("Sample size");
    fireEvent.change(nameInput, { target: { value: "Sample size (n)" } });
    const descriptionInput = screen.getByDisplayValue("Number of participants");
    fireEvent.change(descriptionInput, { target: { value: "Total enrolled" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(mockedApi.updateExtractionField).toHaveBeenCalledWith("1", "f1", {
        name: "Sample size (n)",
        description: "Total enrolled",
      })
    );
    expect(await screen.findByText("Sample size (n)")).toBeInTheDocument();
  });

  it("archives a field and removes it from the active list", async () => {
    mockedApi.listExtractionFields
      .mockResolvedValueOnce([sampleSizeField])
      .mockResolvedValueOnce([]);
    mockedApi.archiveExtractionField.mockResolvedValue({ ...sampleSizeField, archived: true });

    render(<ExtractionFieldsPanel reviewProjectId="1" />);

    fireEvent.click(await screen.findByRole("button", { name: /archive/i }));

    await waitFor(() =>
      expect(mockedApi.archiveExtractionField).toHaveBeenCalledWith("1", "f1")
    );
    await waitFor(() => expect(screen.queryByText("Sample size")).not.toBeInTheDocument());
  });
});
