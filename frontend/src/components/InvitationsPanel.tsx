"use client";

import { useEffect, useRef, useState } from "react";

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
  // Not useListResource: the fetch is conditionally skipped entirely while
  // hasCoReviewer is true, which the hook's always-fetch shape doesn't
  // support. Guards the same reviewProjectId-change race with the same
  // monotonic-token approach, just inlined.
  const latestRequest = useRef(0);

  useEffect(() => {
    if (hasCoReviewer) return;
    const requestId = ++latestRequest.current;
    listInvitations(reviewProjectId)
      .then((result) => {
        if (requestId === latestRequest.current) {
          setInvitations(result);
          setError(null);
        }
      })
      .catch(() => {
        if (requestId === latestRequest.current) {
          setError("Failed to load invitations.");
        }
      });
  }, [reviewProjectId, hasCoReviewer]);

  async function refresh() {
    const requestId = ++latestRequest.current;
    try {
      const result = await listInvitations(reviewProjectId);
      if (requestId === latestRequest.current) {
        setInvitations(result);
        setError(null);
      }
    } catch {
      if (requestId === latestRequest.current) {
        setError("Failed to load invitations.");
      }
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
            <ul className="rows">
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
