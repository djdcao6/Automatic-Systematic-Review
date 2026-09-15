export type MergeMode = "combine" | "keep_first";

export type ReviewProject = {
  id: string;
  name: string;
  criteria_locked: boolean;
  merge_mode: MergeMode;
  created_at: string;
};

export type ReviewProjectInput = {
  name: string;
  merge_mode: MergeMode;
};

export type Criteria = {
  population: string | null;
  intervention: string | null;
  comparison: string | null;
  outcome: string | null;
  exclusion_rules: string[];
  notes: string | null;
};

export type ReviewProjectDetail = ReviewProject & {
  criteria: Criteria | null;
  citations_needing_decision: number;
};

export type CriteriaInput = {
  population: string | null;
  intervention: string | null;
  comparison: string | null;
  outcome: string | null;
  exclusion_rules: string[];
  notes: string | null;
};

export type ExtractionField = {
  id: string;
  name: string;
  description: string | null;
  archived: boolean;
  created_at: string;
  updated_at: string;
};

export type ExtractionFieldInput = {
  name: string;
  description: string | null;
};

export type Citation = {
  id: string;
  title: string;
  abstract: string | null;
  authors: string[];
  year: number | null;
  source: string[];
  needs_abstract: boolean;
};

export type CitationUploadResult = {
  created: number;
  skipped: { row: number; reason: string }[];
};

export type Decision = "include" | "exclude" | "maybe";

export type Suggestion = {
  decision: Decision;
  reason: string;
};

export type ScreeningDecision = {
  decision: Decision;
  reason: string | null;
  created_at: string;
  updated_at: string;
};

export type FullTextParseStatus = "parsed" | "parse_failed";

export type FullText = {
  original_filename: string;
  parse_status: FullTextParseStatus;
  created_at: string;
  updated_at: string;
};

export type FullTextDecision = {
  decision: Decision;
  reason: string | null;
  created_at: string;
  updated_at: string;
};

export type ExtractionValueSuggestion = {
  extraction_field_id: string;
  name: string;
  value: string;
};

export type FullTextSuggestion = {
  decision: Decision;
  reason: string;
  extraction_values: ExtractionValueSuggestion[];
};

export type ExtractionValue = {
  extraction_field_id: string;
  name: string;
  value: string;
  created_at: string;
  updated_at: string;
};

export type CitationDetail = Citation & {
  suggestion: Suggestion | null;
  suggestion_unavailable_reason: string | null;
  screening_decision: ScreeningDecision | null;
  screening_resolved: boolean;
  full_text: FullText | null;
  full_text_decision: FullTextDecision | null;
  full_text_suggestion: FullTextSuggestion | null;
  full_text_suggestion_unavailable_reason: string | null;
  extraction_fields: ExtractionField[];
  extraction_values: ExtractionValue[];
};

export type ScreeningDecisionInput = {
  decision: Decision;
  reason: string | null;
};

export type FullTextDecisionInput = {
  decision: Decision;
  reason: string | null;
};

export type ExtractionValueInput = {
  value: string;
};

export type ConflictFieldName = "screening_decision" | "full_text_decision" | "full_text" | "extraction_value";

export type ConflictField = {
  field: ConflictFieldName;
  extraction_field_id: string | null;
  extraction_field_name: string | null;
};

export type PossibleDuplicateCitation = {
  id: string;
  title: string;
  abstract: string | null;
  authors: string[];
  year: number | null;
  source: string[];
  doi: string | null;
  screening_decision: ScreeningDecision | null;
  full_text_decision: FullTextDecision | null;
  full_text: FullText | null;
  extraction_values: ExtractionValue[];
};

export type PossibleDuplicate = {
  id: string;
  survivor: PossibleDuplicateCitation;
  loser: PossibleDuplicateCitation;
  conflicting_fields: ConflictField[];
  created_at: string;
};

export type ConflictWinner = "survivor" | "loser";

export type ConflictResolutionChoiceInput = {
  field: ConflictFieldName;
  extraction_field_id: string | null;
  winner: ConflictWinner;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function listReviewProjects(): Promise<ReviewProject[]> {
  const response = await fetch(`${API_URL}/review-projects`);
  if (!response.ok) {
    throw new Error("Failed to load review projects");
  }
  return response.json();
}

export async function createReviewProject(
  payload: ReviewProjectInput
): Promise<ReviewProject> {
  const response = await fetch(`${API_URL}/review-projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Failed to create review project");
  }
  return response.json();
}

export async function getReviewProject(id: string): Promise<ReviewProjectDetail> {
  const response = await fetch(`${API_URL}/review-projects/${id}`);
  if (!response.ok) {
    throw new Error("Failed to load review project");
  }
  return response.json();
}

export async function saveCriteria(id: string, payload: CriteriaInput): Promise<Criteria> {
  const response = await fetch(`${API_URL}/review-projects/${id}/criteria`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error("Failed to save criteria");
  }
  return response.json();
}

export async function listExtractionFields(
  reviewProjectId: string
): Promise<ExtractionField[]> {
  const response = await fetch(`${API_URL}/review-projects/${reviewProjectId}/extraction-fields`);
  if (!response.ok) {
    throw new Error("Failed to load extraction fields");
  }
  return response.json();
}

export async function createExtractionField(
  reviewProjectId: string,
  payload: ExtractionFieldInput
): Promise<ExtractionField> {
  const response = await fetch(
    `${API_URL}/review-projects/${reviewProjectId}/extraction-fields`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  if (!response.ok) {
    throw new Error("Failed to create extraction field");
  }
  return response.json();
}

export async function updateExtractionField(
  reviewProjectId: string,
  extractionFieldId: string,
  payload: ExtractionFieldInput
): Promise<ExtractionField> {
  const response = await fetch(
    `${API_URL}/review-projects/${reviewProjectId}/extraction-fields/${extractionFieldId}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  if (!response.ok) {
    throw new Error("Failed to update extraction field");
  }
  return response.json();
}

export async function archiveExtractionField(
  reviewProjectId: string,
  extractionFieldId: string
): Promise<ExtractionField> {
  const response = await fetch(
    `${API_URL}/review-projects/${reviewProjectId}/extraction-fields/${extractionFieldId}/archive`,
    { method: "POST" }
  );
  if (!response.ok) {
    throw new Error("Failed to archive extraction field");
  }
  return response.json();
}

export async function listCitations(reviewProjectId: string): Promise<Citation[]> {
  const response = await fetch(`${API_URL}/review-projects/${reviewProjectId}/citations`);
  if (!response.ok) {
    throw new Error("Failed to load citations");
  }
  return response.json();
}

export async function uploadCitations(
  reviewProjectId: string,
  file: File
): Promise<CitationUploadResult> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`${API_URL}/review-projects/${reviewProjectId}/citations`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    throw new Error("Failed to upload citations");
  }
  return response.json();
}

export async function getCitation(
  reviewProjectId: string,
  citationId: string
): Promise<CitationDetail> {
  const response = await fetch(
    `${API_URL}/review-projects/${reviewProjectId}/citations/${citationId}`
  );
  if (!response.ok) {
    throw new Error("Failed to load citation");
  }
  return response.json();
}

export type ExportedFile = {
  blob: Blob;
  filename: string;
};

export async function exportReviewProject(reviewProjectId: string): Promise<ExportedFile> {
  const response = await fetch(`${API_URL}/review-projects/${reviewProjectId}/export`);
  if (!response.ok) {
    throw new Error("Failed to export review project");
  }
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const filenameMatch = disposition.match(/filename="([^"]+)"/);
  return {
    blob: await response.blob(),
    filename: filenameMatch ? filenameMatch[1] : "citations.csv",
  };
}

export async function uploadFullText(
  reviewProjectId: string,
  citationId: string,
  file: File
): Promise<FullText> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(
    `${API_URL}/review-projects/${reviewProjectId}/citations/${citationId}/full-text`,
    { method: "POST", body: formData }
  );
  if (!response.ok) {
    throw new Error("Failed to upload full text");
  }
  return response.json();
}

export function fullTextFileUrl(reviewProjectId: string, citationId: string): string {
  return `${API_URL}/review-projects/${reviewProjectId}/citations/${citationId}/full-text/file`;
}

export async function recordScreeningDecision(
  reviewProjectId: string,
  citationId: string,
  payload: ScreeningDecisionInput
): Promise<ScreeningDecision> {
  const response = await fetch(
    `${API_URL}/review-projects/${reviewProjectId}/citations/${citationId}/decision`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  if (!response.ok) {
    throw new Error("Failed to record screening decision");
  }
  return response.json();
}

export async function recordFullTextDecision(
  reviewProjectId: string,
  citationId: string,
  payload: FullTextDecisionInput
): Promise<FullTextDecision> {
  const response = await fetch(
    `${API_URL}/review-projects/${reviewProjectId}/citations/${citationId}/full-text-decision`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  if (!response.ok) {
    throw new Error("Failed to record full-text decision");
  }
  return response.json();
}

export async function listPossibleDuplicates(
  reviewProjectId: string
): Promise<PossibleDuplicate[]> {
  const response = await fetch(
    `${API_URL}/review-projects/${reviewProjectId}/possible-duplicates`
  );
  if (!response.ok) {
    throw new Error("Failed to load possible duplicates");
  }
  return response.json();
}

export async function resolvePossibleDuplicate(
  reviewProjectId: string,
  possibleDuplicateId: string,
  choices: ConflictResolutionChoiceInput[]
): Promise<Citation> {
  const response = await fetch(
    `${API_URL}/review-projects/${reviewProjectId}/possible-duplicates/${possibleDuplicateId}/resolve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ choices }),
    }
  );
  if (!response.ok) {
    throw new Error("Failed to resolve possible duplicate");
  }
  return response.json();
}

export async function dismissPossibleDuplicate(
  reviewProjectId: string,
  possibleDuplicateId: string
): Promise<void> {
  const response = await fetch(
    `${API_URL}/review-projects/${reviewProjectId}/possible-duplicates/${possibleDuplicateId}/dismiss`,
    { method: "POST" }
  );
  if (!response.ok) {
    throw new Error("Failed to dismiss possible duplicate");
  }
}

export async function recordExtractionValue(
  reviewProjectId: string,
  citationId: string,
  extractionFieldId: string,
  payload: ExtractionValueInput
): Promise<ExtractionValue> {
  const response = await fetch(
    `${API_URL}/review-projects/${reviewProjectId}/citations/${citationId}` +
      `/extraction-fields/${extractionFieldId}/value`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  if (!response.ok) {
    throw new Error("Failed to record extraction value");
  }
  return response.json();
}
