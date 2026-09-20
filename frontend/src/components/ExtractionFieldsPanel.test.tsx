import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";
import { ExtractionFieldNameTakenError } from "@/lib/api";
import type { ExtractionField } from "@/lib/api";

import { ExtractionFieldsPanel } from "./ExtractionFieldsPanel";

// Automocking would also replace ExtractionFieldNameTakenError's constructor, so an
// instance built in a test would lose its message: keep the real class, mock only
// the functions.
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    listExtractionFields: vi.fn(),
    createExtractionField: vi.fn(),
    updateExtractionField: vi.fn(),
    archiveExtractionField: vi.fn(),
  };
});

const mockedApi = vi.mocked(api);

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

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

  it("shows the backend's message when the name is already taken", async () => {
    const message =
      'An active Extraction Field named "Sample size" already exists in this Review Project';
    mockedApi.createExtractionField.mockRejectedValue(new ExtractionFieldNameTakenError(message));

    render(<ExtractionFieldsPanel reviewProjectId="1" />);

    await waitFor(() => expect(mockedApi.listExtractionFields).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "Sample size" } });
    fireEvent.click(screen.getByRole("button", { name: /add field/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    // The Reviewer's input is kept, so they can change the name and try again.
    expect(screen.getByLabelText(/^name$/i)).toHaveValue("Sample size");
  });

  it("shows the backend's message when a rename collides, and keeps the edit form open", async () => {
    const message =
      'An active Extraction Field named "Follow-up" already exists in this Review Project';
    mockedApi.listExtractionFields.mockResolvedValue([sampleSizeField]);
    mockedApi.updateExtractionField.mockRejectedValue(new ExtractionFieldNameTakenError(message));

    render(<ExtractionFieldsPanel reviewProjectId="1" />);

    fireEvent.click(await screen.findByRole("button", { name: /edit/i }));
    fireEvent.change(screen.getByDisplayValue("Sample size"), { target: { value: "Follow-up" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(screen.getByDisplayValue("Follow-up")).toBeInTheDocument();
  });

  it("clears the name-taken message after a successful add", async () => {
    mockedApi.createExtractionField
      .mockRejectedValueOnce(new ExtractionFieldNameTakenError("Name taken already"))
      .mockResolvedValueOnce(sampleSizeField);

    render(<ExtractionFieldsPanel reviewProjectId="1" />);

    await waitFor(() => expect(mockedApi.listExtractionFields).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "Sample size" } });
    fireEvent.click(screen.getByRole("button", { name: /add field/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Name taken already");

    fireEvent.change(screen.getByLabelText(/^name$/i), { target: { value: "Follow-up" } });
    fireEvent.click(screen.getByRole("button", { name: /add field/i }));

    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
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

  it("ignores a stale response after reviewProjectId changes before it resolves", async () => {
    const first = deferred<ExtractionField[]>();
    const second = deferred<ExtractionField[]>();
    mockedApi.listExtractionFields
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);

    const { rerender } = render(<ExtractionFieldsPanel reviewProjectId="1" />);
    rerender(<ExtractionFieldsPanel reviewProjectId="2" />);

    await act(async () => {
      second.resolve([{ ...sampleSizeField, id: "b", name: "Project B Field" }]);
    });
    expect(await screen.findByText("Project B Field")).toBeInTheDocument();

    await act(async () => {
      first.resolve([{ ...sampleSizeField, id: "a", name: "Project A Field" }]);
    });
    expect(screen.queryByText("Project A Field")).not.toBeInTheDocument();
  });
  describe("when there are no extraction fields", () => {
    it("says so, and points at the form below", async () => {
      mockedApi.listExtractionFields.mockResolvedValue([]);

      render(<ExtractionFieldsPanel reviewProjectId="1" />);

      expect(
        await screen.findByText("No extraction fields yet. Add one below.")
      ).toBeInTheDocument();
      expect(screen.queryAllByRole("listitem")).toHaveLength(0);
    });

    it("stays quiet while the list is still loading", async () => {
      const pending = deferred<ExtractionField[]>();
      mockedApi.listExtractionFields.mockReturnValueOnce(pending.promise);

      render(<ExtractionFieldsPanel reviewProjectId="1" />);

      expect(screen.queryByText(/no extraction fields yet/i)).not.toBeInTheDocument();
      await act(async () => pending.resolve([]));
      expect(await screen.findByText(/no extraction fields yet/i)).toBeInTheDocument();
    });

    it("does not claim the list is empty when it failed to load", async () => {
      mockedApi.listExtractionFields.mockRejectedValueOnce(new Error("down"));

      render(<ExtractionFieldsPanel reviewProjectId="1" />);

      expect(await screen.findByText(/failed to load extraction fields/i)).toBeInTheDocument();
      expect(screen.queryByText(/no extraction fields yet/i)).not.toBeInTheDocument();
    });

    it("goes away once there is a field", async () => {
      mockedApi.listExtractionFields.mockResolvedValue([sampleSizeField]);

      render(<ExtractionFieldsPanel reviewProjectId="1" />);

      expect(await screen.findByText("Sample size")).toBeInTheDocument();
      expect(screen.queryByText(/no extraction fields yet/i)).not.toBeInTheDocument();
    });
  });
});
