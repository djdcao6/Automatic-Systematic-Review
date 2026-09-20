import { clearToken, getToken } from "@/lib/auth";

export type Reviewer = {
  id: string;
  email: string;
  created_at: string;
  // When the Reviewer accepted the AI disclosure. Null on an account that pre-dates
  // the notice: it is asked once, before its first AI request.
  ai_consent_at: string | null;
};

export type ReviewerInput = {
  email: string;
  password: string;
};

// Signing up also needs the Reviewer's agreement to the AI disclosure (#61).
export type RegisterInput = ReviewerInput & { ai_consent: boolean };

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

export type SearchTerms = {
  population_terms: string[];
  intervention_terms: string[];
  comparison_terms: string[];
  outcome_terms: string[];
  combined_query: string;
};

export type SearchTermsInput = {
  population_terms: string[];
  intervention_terms: string[];
  comparison_terms: string[];
  outcome_terms: string[];
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

// What generating an AI Suggestion on demand produced. Both fields are null for
// a blind Reviewer: the suggestion is kept for them, but nothing about it is sent.
export type SuggestionOutcome = {
  suggestion: Suggestion | null;
  suggestion_unavailable_reason: string | null;
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
  // The model was shown only the start of a long PDF.
  truncated: boolean;
};

// What generating a Full-Text Suggestion on demand produced. Both fields are null
// when the Full Text was replaced while the model was reading the old one: nothing
// was kept, so the page looks again.
export type FullTextSuggestionOutcome = {
  suggestion: FullTextSuggestion | null;
  suggestion_unavailable_reason: string | null;
};

export type ExtractionValue = {
  extraction_field_id: string;
  name: string;
  value: string;
  created_at: string;
  updated_at: string;
};

export type CitationDetail = Citation & {
  // Place among the project's active citations, for stepping through them.
  // `position` is null for an archived citation, which is not in the list.
  position: number | null;
  total: number;
  previous_citation_id: string | null;
  next_citation_id: string | null;
  suggestion: Suggestion | null;
  suggestion_unavailable_reason: string | null;
  // True when no suggestion exists yet and one can be generated: the page asks
  // for it separately (`generateSuggestion`) so this response never waits on the model.
  suggestion_needs_generation: boolean;
  screening_decision: ScreeningDecision | null;
  peer_screening_decision: ScreeningDecision | null;
  screening_blind: boolean;
  screening_resolved: boolean;
  full_text: FullText | null;
  full_text_decision: FullTextDecision | null;
  full_text_suggestion: FullTextSuggestion | null;
  full_text_suggestion_unavailable_reason: string | null;
  // True when a Full Text was parsed and no suggestion exists yet: the page asks
  // for it separately (`generateFullTextSuggestion`) so this response never waits on the model.
  full_text_suggestion_needs_generation: boolean;
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

// FastAPI reports request-validation failures (422) as a list of
// { loc, msg } objects instead of a string; label each message with the
// field it's about (the last `loc` entry, skipping the leading "body").
function validationMessage(detail: unknown[]): string | null {
  const messages = detail.flatMap((issue) => {
    const { loc, msg } = (issue ?? {}) as { loc?: unknown; msg?: unknown };
    if (typeof msg !== "string") return [];
    const field = Array.isArray(loc) ? loc.filter((part) => part !== "body").at(-1) : undefined;
    return [field === undefined ? msg : `${field}: ${msg}`];
  });
  return messages.length > 0 ? messages.join("; ") : null;
}

async function errorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail)) {
      const message = validationMessage(body.detail);
      if (message) return message;
    }
  } catch {
    // response body wasn't JSON; fall through to the generic message
  }
  return fallback;
}

// The one seam every request response passes through before its body is
// touched: whatever the backend sent as `detail` on a non-2xx response is
// what callers see, instead of each call site deciding for itself whether to
// bother reading it.
async function ensureOk(response: Response, fallback: string): Promise<Response> {
  if (!response.ok) {
    throw new Error(await errorMessage(response, fallback));
  }
  return response;
}

// Convenience for the common case (authenticated endpoint, JSON body, JSON
// response) that most exported functions below reduce to.
async function request<T>(input: string, init: RequestInit, fallback: string): Promise<T> {
  const response = await ensureOk(await authorizedFetch(input, init), fallback);
  return response.json();
}

// Same as `request`, but for the handful of endpoints a Reviewer hits before
// they're authenticated (register/login/invitation acceptance), which use
// plain fetch rather than authorizedFetch so a 401 there (e.g. a wrong
// password) never triggers the token-expiry redirect.
async function publicRequest<T>(input: string, init: RequestInit, fallback: string): Promise<T> {
  const response = await ensureOk(await fetch(input, init), fallback);
  return response.json();
}

export async function registerReviewer(payload: RegisterInput): Promise<Reviewer> {
  return publicRequest(
    `${API_URL}/register`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    "Failed to register"
  );
}

export async function loginReviewer(payload: ReviewerInput): Promise<AuthToken> {
  return publicRequest(
    `${API_URL}/login`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    "Failed to log in"
  );
}

export async function getMe(): Promise<Reviewer> {
  return request(`${API_URL}/me`, {}, "Failed to load current reviewer");
}

// Records that an account that pre-dates the AI disclosure has accepted it (#61).
export async function acceptAiConsent(): Promise<Reviewer> {
  return request(
    `${API_URL}/me/ai-consent`,
    { method: "POST" },
    "Failed to record your agreement"
  );
}

export async function listReviewProjects(): Promise<ReviewProject[]> {
  return request(`${API_URL}/review-projects`, {}, "Failed to load review projects");
}

// Thrown instead of a plain Error when creation is blocked by the Free
// Plan's Review-Project cap (#41), so callers can point the Reviewer at the
// Account/Billing page rather than showing a generic failure message.
export class ReviewProjectCapError extends Error {}

export async function createReviewProject(
  payload: ReviewProjectInput
): Promise<ReviewProject> {
  const response = await authorizedFetch(`${API_URL}/review-projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (response.status === 403) {
    throw new ReviewProjectCapError(
      await errorMessage(response, "Free Plan is limited to 1 Review Project.")
    );
  }
  return (await ensureOk(response, "Failed to create review project")).json();
}

export async function getReviewProject(id: string): Promise<ReviewProjectDetail> {
  return request(`${API_URL}/review-projects/${id}`, {}, "Failed to load review project");
}

export async function saveCriteria(id: string, payload: CriteriaInput): Promise<Criteria> {
  return request(
    `${API_URL}/review-projects/${id}/criteria`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    "Failed to save criteria"
  );
}

export async function generateSearchTerms(reviewProjectId: string): Promise<SearchTerms> {
  return request(
    `${API_URL}/review-projects/${reviewProjectId}/search-terms`,
    { method: "POST" },
    "Failed to generate search terms"
  );
}

// Returns null when no Search Terms have been generated yet (backend 404),
// rather than treating "none generated yet" as a load failure.
export async function getSearchTerms(reviewProjectId: string): Promise<SearchTerms | null> {
  const response = await authorizedFetch(
    `${API_URL}/review-projects/${reviewProjectId}/search-terms`
  );
  if (response.status === 404) return null;
  return (await ensureOk(response, "Failed to load search terms")).json();
}

export async function updateSearchTerms(
  reviewProjectId: string,
  payload: SearchTermsInput
): Promise<SearchTerms> {
  return request(
    `${API_URL}/review-projects/${reviewProjectId}/search-terms`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    "Failed to update search terms"
  );
}

export async function listExtractionFields(
  reviewProjectId: string
): Promise<ExtractionField[]> {
  return request(
    `${API_URL}/review-projects/${reviewProjectId}/extraction-fields`,
    {},
    "Failed to load extraction fields"
  );
}

// Thrown instead of a plain Error when another active Extraction Field in the
// Review Project already has the name (#67), so the form can show the
// backend's message as it is while other failures keep a generic one.
export class ExtractionFieldNameTakenError extends Error {}

async function extractionFieldRequest(
  input: string,
  init: RequestInit,
  fallback: string
): Promise<ExtractionField> {
  const response = await authorizedFetch(input, init);
  if (response.status === 409) {
    throw new ExtractionFieldNameTakenError(await errorMessage(response, fallback));
  }
  return (await ensureOk(response, fallback)).json();
}

export async function createExtractionField(
  reviewProjectId: string,
  payload: ExtractionFieldInput
): Promise<ExtractionField> {
  return extractionFieldRequest(
    `${API_URL}/review-projects/${reviewProjectId}/extraction-fields`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    "Failed to create extraction field"
  );
}

export async function updateExtractionField(
  reviewProjectId: string,
  extractionFieldId: string,
  payload: ExtractionFieldInput
): Promise<ExtractionField> {
  return extractionFieldRequest(
    `${API_URL}/review-projects/${reviewProjectId}/extraction-fields/${extractionFieldId}`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    "Failed to update extraction field"
  );
}

export async function archiveExtractionField(
  reviewProjectId: string,
  extractionFieldId: string
): Promise<ExtractionField> {
  return request(
    `${API_URL}/review-projects/${reviewProjectId}/extraction-fields/${extractionFieldId}/archive`,
    { method: "POST" },
    "Failed to archive extraction field"
  );
}

export async function listCitations(reviewProjectId: string): Promise<Citation[]> {
  return request(
    `${API_URL}/review-projects/${reviewProjectId}/citations`,
    {},
    "Failed to load citations"
  );
}

export async function uploadCitations(
  reviewProjectId: string,
  file: File
): Promise<CitationUploadResult> {
  const formData = new FormData();
  formData.append("file", file);
  return request(
    `${API_URL}/review-projects/${reviewProjectId}/citations`,
    { method: "POST", body: formData },
    "Failed to upload citations"
  );
}

export async function getCitation(
  reviewProjectId: string,
  citationId: string
): Promise<CitationDetail> {
  return request(
    `${API_URL}/review-projects/${reviewProjectId}/citations/${citationId}`,
    {},
    "Failed to load citation"
  );
}

export async function generateSuggestion(
  reviewProjectId: string,
  citationId: string
): Promise<SuggestionOutcome> {
  return request(
    `${API_URL}/review-projects/${reviewProjectId}/citations/${citationId}/suggestion`,
    { method: "POST" },
    "Failed to generate AI suggestion"
  );
}

export async function generateFullTextSuggestion(
  reviewProjectId: string,
  citationId: string
): Promise<FullTextSuggestionOutcome> {
  return request(
    `${API_URL}/review-projects/${reviewProjectId}/citations/${citationId}/full-text-suggestion`,
    { method: "POST" },
    "Failed to generate Full-Text Suggestion"
  );
}

export type FlowDiagram = {
  criteria: Criteria | null;
  identification_counts: Record<string, number>;
  duplicates_removed: number;
  screened: number;
  excluded: number;
  pending: number;
  full_text_assessed: number;
  full_text_excluded_by_reason: Record<string, number>;
  full_text_included: number;
  full_text_pending: number;
};

export async function getFlowDiagram(reviewProjectId: string): Promise<FlowDiagram> {
  return request(
    `${API_URL}/review-projects/${reviewProjectId}/flow-diagram`,
    {},
    "Failed to load flow diagram"
  );
}

export type ExportedFile = {
  blob: Blob;
  filename: string;
};

export async function exportReviewProject(reviewProjectId: string): Promise<ExportedFile> {
  const response = await ensureOk(
    await authorizedFetch(`${API_URL}/review-projects/${reviewProjectId}/export`),
    "Failed to export review project"
  );
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
  return request(
    `${API_URL}/review-projects/${reviewProjectId}/citations/${citationId}/full-text`,
    { method: "POST", body: formData },
    "Failed to upload full text"
  );
}

// A plain <a href> can't carry the Authorization header this endpoint now
// requires (#24), so the file is fetched and handed to the caller as a Blob
// to open via an object URL instead.
export async function fetchFullTextFile(
  reviewProjectId: string,
  citationId: string
): Promise<Blob> {
  const response = await ensureOk(
    await authorizedFetch(
      `${API_URL}/review-projects/${reviewProjectId}/citations/${citationId}/full-text/file`
    ),
    "Failed to load full text file"
  );
  return response.blob();
}

export async function recordScreeningDecision(
  reviewProjectId: string,
  citationId: string,
  payload: ScreeningDecisionInput
): Promise<ScreeningDecision> {
  return request(
    `${API_URL}/review-projects/${reviewProjectId}/citations/${citationId}/decision`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    "Failed to record screening decision"
  );
}

export async function recordFullTextDecision(
  reviewProjectId: string,
  citationId: string,
  payload: FullTextDecisionInput
): Promise<FullTextDecision> {
  return request(
    `${API_URL}/review-projects/${reviewProjectId}/citations/${citationId}/full-text-decision`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    "Failed to record full-text decision"
  );
}

export async function listPossibleDuplicates(
  reviewProjectId: string
): Promise<PossibleDuplicate[]> {
  return request(
    `${API_URL}/review-projects/${reviewProjectId}/possible-duplicates`,
    {},
    "Failed to load possible duplicates"
  );
}

export async function resolvePossibleDuplicate(
  reviewProjectId: string,
  possibleDuplicateId: string,
  choices: ConflictResolutionChoiceInput[]
): Promise<Citation> {
  return request(
    `${API_URL}/review-projects/${reviewProjectId}/possible-duplicates/${possibleDuplicateId}/resolve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ choices }),
    },
    "Failed to resolve possible duplicate"
  );
}

export async function dismissPossibleDuplicate(
  reviewProjectId: string,
  possibleDuplicateId: string
): Promise<void> {
  await ensureOk(
    await authorizedFetch(
      `${API_URL}/review-projects/${reviewProjectId}/possible-duplicates/${possibleDuplicateId}/dismiss`,
      { method: "POST" }
    ),
    "Failed to dismiss possible duplicate"
  );
}

export async function listConflicts(reviewProjectId: string): Promise<Conflict[]> {
  return request(
    `${API_URL}/review-projects/${reviewProjectId}/conflicts`,
    {},
    "Failed to load conflicts"
  );
}

export async function resolveConflict(
  reviewProjectId: string,
  conflictId: string,
  payload: ConflictResolveInput
): Promise<ConflictResolved> {
  return request(
    `${API_URL}/review-projects/${reviewProjectId}/conflicts/${conflictId}/resolve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    "Failed to resolve conflict"
  );
}

export async function listInvitations(reviewProjectId: string): Promise<Invitation[]> {
  return request(
    `${API_URL}/review-projects/${reviewProjectId}/invitations`,
    {},
    "Failed to load invitations"
  );
}

export async function createInvitation(reviewProjectId: string): Promise<Invitation> {
  return request(
    `${API_URL}/review-projects/${reviewProjectId}/invitations`,
    { method: "POST" },
    "Failed to generate invitation"
  );
}

export async function revokeInvitation(
  reviewProjectId: string,
  invitationId: string
): Promise<Invitation> {
  return request(
    `${API_URL}/review-projects/${reviewProjectId}/invitations/${invitationId}/revoke`,
    { method: "POST" },
    "Failed to revoke invitation"
  );
}

export async function removeCoReviewer(reviewProjectId: string): Promise<ReviewProject> {
  return request(
    `${API_URL}/review-projects/${reviewProjectId}/co-reviewer/remove`,
    { method: "POST" },
    "Failed to remove Co-Reviewer"
  );
}

// Unauthenticated: the recipient doesn't have an account yet when they open
// the invite link, so these three calls (unlike everything else in this
// file) don't go through authorizedFetch.

export async function getInvitationPublic(token: string): Promise<InvitationPublic> {
  return publicRequest(`${API_URL}/invitations/${token}`, {}, "Failed to load invitation");
}

export async function acceptInvitationByRegistering(
  token: string,
  payload: RegisterInput
): Promise<InvitationAcceptResult> {
  return publicRequest(
    `${API_URL}/invitations/${token}/accept-register`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    "Failed to accept invitation"
  );
}

export async function acceptInvitationByLoggingIn(
  token: string,
  payload: ReviewerInput
): Promise<InvitationAcceptResult> {
  return publicRequest(
    `${API_URL}/invitations/${token}/accept-login`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    "Failed to accept invitation"
  );
}

export type Plan = "free" | "paid";

export type Subscription = {
  plan: Plan;
  status: string | null;
};

// Returns null when billing is disabled (backend 404) rather than treating
// the dark-launch flag-off state as a load failure — callers use null to
// keep all billing UI hidden, per #39.
export async function getMySubscription(): Promise<Subscription | null> {
  const response = await authorizedFetch(`${API_URL}/me/subscription`);
  if (response.status === 404) return null;
  return (await ensureOk(response, "Failed to load subscription")).json();
}

export type CheckoutSession = {
  url: string;
};

export async function createCheckoutSession(): Promise<CheckoutSession> {
  return request(
    `${API_URL}/billing/checkout-session`,
    { method: "POST" },
    "Failed to start checkout"
  );
}

export type PortalSession = {
  url: string;
};

export async function createPortalSession(): Promise<PortalSession> {
  return request(
    `${API_URL}/billing/portal-session`,
    { method: "POST" },
    "Failed to open billing portal"
  );
}

export async function recordExtractionValue(
  reviewProjectId: string,
  citationId: string,
  extractionFieldId: string,
  payload: ExtractionValueInput
): Promise<ExtractionValue> {
  return request(
    `${API_URL}/review-projects/${reviewProjectId}/citations/${citationId}` +
      `/extraction-fields/${extractionFieldId}/value`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    "Failed to record extraction value"
  );
}
