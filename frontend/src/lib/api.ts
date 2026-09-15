import { clearToken, getToken } from "@/lib/auth";

export type Reviewer = {
  id: string;
  email: string;
  created_at: string;
};

export type ReviewerInput = {
  email: string;
  password: string;
};

export type AuthToken = {
  access_token: string;
  token_type: string;
};

export type MergeMode = "combine" | "keep_first";

export type ReviewMode = "solo" | "dual";

export type ReviewProject = {
  id: string;
  name: string;
  criteria_locked: boolean;
  merge_mode: MergeMode;
  review_mode: ReviewMode;
  owner_reviewer_id: string;
  co_reviewer_id: string | null;
  created_at: string;
};

export type ReviewProjectInput = {
  name: string;
  merge_mode: MergeMode;
  review_mode: ReviewMode;
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
  blocked_pending_co_reviewer: boolean;
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
  peer_screening_decision: ScreeningDecision | null;
  screening_blind: boolean;
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

export type ConflictCitation = {
  id: string;
  title: string;
};

export type Conflict = {
  id: string;
  citation: ConflictCitation;
  owner_decision: ScreeningDecision;
  co_reviewer_decision: ScreeningDecision;
  created_at: string;
};

export type ConflictResolveInput = {
  decision: Decision;
  reason: string | null;
};

export type ConflictResolved = {
  id: string;
  status: "resolved";
  resolved_decision: Decision;
  resolved_reason: string | null;
  resolved_at: string;
};

export type InvitationStatus = "pending" | "accepted" | "revoked";

export type Invitation = {
  id: string;
  token: string;
  status: InvitationStatus;
  created_at: string;
};

export type InvitationPublic = {
  review_project_name: string;
  status: InvitationStatus;
};

export type InvitationAcceptResult = {
  access_token: string;
  token_type: string;
  review_project_id: string;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function redirectToLogin(): void {
  clearToken();
  if (typeof window !== "undefined") {
    // This module sits below React (no router instance available here), so
    // a hard navigation is the only option for routing an expired session
    // to login regardless of which page/component triggered the request.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = "/login";
  }
}

// Every endpoint below except register/login requires a JWT (#24). This
// wrapper attaches the stored token to each request and, on a 401 (missing,
// invalid, or expired token), clears it and routes the Reviewer to login
// instead of letting each call site handle that individually.
async function authorizedFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(input, { ...init, headers });
  if (response.status === 401) {
    redirectToLogin();
  }
  return response;
}

async function errorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") return body.detail;
  } catch {
    // response body wasn't JSON; fall through to the generic message
  }
  return fallback;
}

export async function registerReviewer(payload: ReviewerInput): Promise<Reviewer> {
  const response = await fetch(`${API_URL}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response, "Failed to register"));
  }
  return response.json();
}

export async function loginReviewer(payload: ReviewerInput): Promise<AuthToken> {
  const response = await fetch(`${API_URL}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response, "Failed to log in"));
  }
  return response.json();
}

export async function getMe(): Promise<Reviewer> {
  const response = await authorizedFetch(`${API_URL}/me`);
  if (!response.ok) {
    throw new Error("Failed to load current reviewer");
  }
  return response.json();
}

export async function listReviewProjects(): Promise<ReviewProject[]> {
  const response = await authorizedFetch(`${API_URL}/review-projects`);
  if (!response.ok) {
    throw new Error("Failed to load review projects");
  }
  return response.json();
}

export async function createReviewProject(
  payload: ReviewProjectInput
): Promise<ReviewProject> {
  const response = await authorizedFetch(`${API_URL}/review-projects`, {
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
  const response = await authorizedFetch(`${API_URL}/review-projects/${id}`);
  if (!response.ok) {
    throw new Error("Failed to load review project");
  }
  return response.json();
}

export async function saveCriteria(id: string, payload: CriteriaInput): Promise<Criteria> {
  const response = await authorizedFetch(`${API_URL}/review-projects/${id}/criteria`, {
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
  const response = await authorizedFetch(`${API_URL}/review-projects/${reviewProjectId}/extraction-fields`);
  if (!response.ok) {
    throw new Error("Failed to load extraction fields");
  }
  return response.json();
}

export async function createExtractionField(
  reviewProjectId: string,
  payload: ExtractionFieldInput
): Promise<ExtractionField> {
  const response = await authorizedFetch(
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
  const response = await authorizedFetch(
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
  const response = await authorizedFetch(
    `${API_URL}/review-projects/${reviewProjectId}/extraction-fields/${extractionFieldId}/archive`,
    { method: "POST" }
  );
  if (!response.ok) {
    throw new Error("Failed to archive extraction field");
  }
  return response.json();
}

export async function listCitations(reviewProjectId: string): Promise<Citation[]> {
  const response = await authorizedFetch(`${API_URL}/review-projects/${reviewProjectId}/citations`);
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
  const response = await authorizedFetch(`${API_URL}/review-projects/${reviewProjectId}/citations`, {
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
  const response = await authorizedFetch(
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
  const response = await authorizedFetch(`${API_URL}/review-projects/${reviewProjectId}/export`);
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
  const response = await authorizedFetch(
    `${API_URL}/review-projects/${reviewProjectId}/citations/${citationId}/full-text`,
    { method: "POST", body: formData }
  );
  if (!response.ok) {
    throw new Error("Failed to upload full text");
  }
  return response.json();
}

// A plain <a href> can't carry the Authorization header this endpoint now
// requires (#24), so the file is fetched and handed to the caller as a Blob
// to open via an object URL instead.
export async function fetchFullTextFile(
  reviewProjectId: string,
  citationId: string
): Promise<Blob> {
  const response = await authorizedFetch(
    `${API_URL}/review-projects/${reviewProjectId}/citations/${citationId}/full-text/file`
  );
  if (!response.ok) {
    throw new Error("Failed to load full text file");
  }
  return response.blob();
}

export async function recordScreeningDecision(
  reviewProjectId: string,
  citationId: string,
  payload: ScreeningDecisionInput
): Promise<ScreeningDecision> {
  const response = await authorizedFetch(
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
  const response = await authorizedFetch(
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
  const response = await authorizedFetch(
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
  const response = await authorizedFetch(
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
  const response = await authorizedFetch(
    `${API_URL}/review-projects/${reviewProjectId}/possible-duplicates/${possibleDuplicateId}/dismiss`,
    { method: "POST" }
  );
  if (!response.ok) {
    throw new Error("Failed to dismiss possible duplicate");
  }
}

export async function listConflicts(reviewProjectId: string): Promise<Conflict[]> {
  const response = await authorizedFetch(`${API_URL}/review-projects/${reviewProjectId}/conflicts`);
  if (!response.ok) {
    throw new Error("Failed to load conflicts");
  }
  return response.json();
}

export async function resolveConflict(
  reviewProjectId: string,
  conflictId: string,
  payload: ConflictResolveInput
): Promise<ConflictResolved> {
  const response = await authorizedFetch(
    `${API_URL}/review-projects/${reviewProjectId}/conflicts/${conflictId}/resolve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  if (!response.ok) {
    throw new Error(await errorMessage(response, "Failed to resolve conflict"));
  }
  return response.json();
}

export async function listInvitations(reviewProjectId: string): Promise<Invitation[]> {
  const response = await authorizedFetch(
    `${API_URL}/review-projects/${reviewProjectId}/invitations`
  );
  if (!response.ok) {
    throw new Error("Failed to load invitations");
  }
  return response.json();
}

export async function createInvitation(reviewProjectId: string): Promise<Invitation> {
  const response = await authorizedFetch(
    `${API_URL}/review-projects/${reviewProjectId}/invitations`,
    { method: "POST" }
  );
  if (!response.ok) {
    throw new Error(await errorMessage(response, "Failed to generate invitation"));
  }
  return response.json();
}

export async function revokeInvitation(
  reviewProjectId: string,
  invitationId: string
): Promise<Invitation> {
  const response = await authorizedFetch(
    `${API_URL}/review-projects/${reviewProjectId}/invitations/${invitationId}/revoke`,
    { method: "POST" }
  );
  if (!response.ok) {
    throw new Error("Failed to revoke invitation");
  }
  return response.json();
}

export async function removeCoReviewer(reviewProjectId: string): Promise<ReviewProject> {
  const response = await authorizedFetch(
    `${API_URL}/review-projects/${reviewProjectId}/co-reviewer/remove`,
    { method: "POST" }
  );
  if (!response.ok) {
    throw new Error(await errorMessage(response, "Failed to remove Co-Reviewer"));
  }
  return response.json();
}

// Unauthenticated: the recipient doesn't have an account yet when they open
// the invite link, so these three calls (unlike everything else in this
// file) don't go through authorizedFetch.

export async function getInvitationPublic(token: string): Promise<InvitationPublic> {
  const response = await fetch(`${API_URL}/invitations/${token}`);
  if (!response.ok) {
    throw new Error(await errorMessage(response, "Failed to load invitation"));
  }
  return response.json();
}

export async function acceptInvitationByRegistering(
  token: string,
  payload: ReviewerInput
): Promise<InvitationAcceptResult> {
  const response = await fetch(`${API_URL}/invitations/${token}/accept-register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response, "Failed to accept invitation"));
  }
  return response.json();
}

export async function acceptInvitationByLoggingIn(
  token: string,
  payload: ReviewerInput
): Promise<InvitationAcceptResult> {
  const response = await fetch(`${API_URL}/invitations/${token}/accept-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response, "Failed to accept invitation"));
  }
  return response.json();
}

export async function recordExtractionValue(
  reviewProjectId: string,
  citationId: string,
  extractionFieldId: string,
  payload: ExtractionValueInput
): Promise<ExtractionValue> {
  const response = await authorizedFetch(
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
