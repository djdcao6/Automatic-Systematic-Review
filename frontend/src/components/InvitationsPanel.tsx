"use client";

import { useEffect, useState } from "react";

import {
  createInvitation,
  listInvitations,
  removeCoReviewer,
  revokeInvitation,
  type Invitation,
} from "@/lib/api";

function invitationLink(token: string): string {
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return `${origin}/invitations/${token}`;
}

export function InvitationsPanel({
  reviewProjectId,
  hasCoReviewer,
  onCoReviewerRemoved,
}: {
  reviewProjectId: string;
  hasCoReviewer: boolean;
  onCoReviewerRemoved?: () => void;
}) {
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (hasCoReviewer) return;
    listInvitations(reviewProjectId)
      .then(setInvitations)
      .catch(() => setError("Failed to load invitations."));
  }, [reviewProjectId, hasCoReviewer]);

  async function refresh() {
    try {
      setInvitations(await listInvitations(reviewProjectId));
      setError(null);
    } catch {
      setError("Failed to load invitations.");
    }
  }

  async function handleGenerate() {
    try {
      await createInvitation(reviewProjectId);
      setError(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate invitation.");
    }
  }

  async function handleRevoke(invitationId: string) {
    try {
      await revokeInvitation(reviewProjectId, invitationId);
      setError(null);
      await refresh();
    } catch {
      setError("Failed to revoke invitation.");
    }
  }

  async function handleRemove() {
    try {
      await removeCoReviewer(reviewProjectId);
      setError(null);
      onCoReviewerRemoved?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove Co-Reviewer.");
    }
  }

  return (
    <section>
      <h2>Co-Reviewer</h2>
      {error && <p role="alert">{error}</p>}
      {hasCoReviewer ? (
        <>
          <p>A Co-Reviewer has joined this Review Project.</p>
          <button type="button" onClick={handleRemove}>
            Remove Co-Reviewer
          </button>
        </>
      ) : (
        <>
          {invitations.length === 0 ? (
            <button type="button" onClick={handleGenerate}>
              Generate Invite Link
            </button>
          ) : (
            <ul>
              {invitations.map((invitation) => (
                <li key={invitation.id}>
                  <input readOnly value={invitationLink(invitation.token)} />
                  <button type="button" onClick={() => handleRevoke(invitation.id)}>
                    Revoke
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
