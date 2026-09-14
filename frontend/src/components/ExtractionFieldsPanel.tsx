"use client";

import { useEffect, useState, type FormEvent } from "react";

import {
  archiveExtractionField,
  createExtractionField,
  listExtractionFields,
  updateExtractionField,
  type ExtractionField,
  type ExtractionFieldInput,
} from "@/lib/api";

function blankOrValue(value: string): string | null {
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function EditFieldForm({
  field,
  onSave,
  onCancel,
}: {
  field: ExtractionField;
  onSave: (input: ExtractionFieldInput) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState(field.name);
  const [description, setDescription] = useState(field.description ?? "");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSave({ name, description: blankOrValue(description) });
  }

  return (
    <form onSubmit={handleSubmit}>
      <label htmlFor={`edit-name-${field.id}`}>Name</label>
      <input
        id={`edit-name-${field.id}`}
        value={name}
        onChange={(event) => setName(event.target.value)}
      />

      <label htmlFor={`edit-description-${field.id}`}>Description</label>
      <input
        id={`edit-description-${field.id}`}
        value={description}
        onChange={(event) => setDescription(event.target.value)}
      />

      <button type="submit">Save</button>
      <button type="button" onClick={onCancel}>
        Cancel
      </button>
    </form>
  );
}

export function ExtractionFieldsPanel({ reviewProjectId }: { reviewProjectId: string }) {
  const [fields, setFields] = useState<ExtractionField[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listExtractionFields(reviewProjectId)
      .then(setFields)
      .catch(() => setError("Failed to load extraction fields."));
  }, [reviewProjectId]);

  async function refresh() {
    setFields(await listExtractionFields(reviewProjectId));
  }

  async function handleAddField(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    try {
      await createExtractionField(reviewProjectId, {
        name,
        description: blankOrValue(description),
      });
      setName("");
      setDescription("");
      setError(null);
      await refresh();
    } catch {
      setError("Failed to add extraction field.");
    }
  }

  async function handleSaveEdit(fieldId: string, input: ExtractionFieldInput) {
    try {
      await updateExtractionField(reviewProjectId, fieldId, input);
      setEditingId(null);
      setError(null);
      await refresh();
    } catch {
      setError("Failed to update extraction field.");
    }
  }

  async function handleArchive(fieldId: string) {
    try {
      await archiveExtractionField(reviewProjectId, fieldId);
      setError(null);
      await refresh();
    } catch {
      setError("Failed to archive extraction field.");
    }
  }

  return (
    <section>
      <h2>Extraction Fields</h2>
      {error && <p role="alert">{error}</p>}

      <ul>
        {fields.map((field) =>
          editingId === field.id ? (
            <li key={field.id}>
              <EditFieldForm
                field={field}
                onSave={(input) => handleSaveEdit(field.id, input)}
                onCancel={() => setEditingId(null)}
              />
            </li>
          ) : (
            <li key={field.id}>
              <strong>{field.name}</strong>
              {field.description && <p>{field.description}</p>}
              <button type="button" onClick={() => setEditingId(field.id)}>
                Edit
              </button>
              <button type="button" onClick={() => handleArchive(field.id)}>
                Archive
              </button>
            </li>
          )
        )}
      </ul>

      <form onSubmit={handleAddField}>
        <label htmlFor="extraction-field-name">Name</label>
        <input
          id="extraction-field-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />

        <label htmlFor="extraction-field-description">Description</label>
        <input
          id="extraction-field-description"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />

        <button type="submit">Add Field</button>
      </form>
    </section>
  );
}
