"use client";

import { useState } from "react";

import { AI_DISCLOSURE } from "@/components/AiConsentField";
import { acceptAiConsent } from "@/lib/api";

// Shown once to an account that pre-dates the AI disclosure (#61), in place of the
// project page, so nothing behind it can send a request to the model first.
export function AiConsentDialog({ onAccepted }: { onAccepted: () => void }) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleAccept() {
    setSaving(true);
    setError(null);
    try {
      await acceptAiConsent();
      onAccepted();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to record your agreement");
      setSaving(false);
    }
  }

  return (
    <main className="auth">
      <h1 id="ai-consent-title">Before you continue</h1>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="ai-consent-title"
        className="panel"
      >
        <p>{AI_DISCLOSURE}</p>
        {error && <p role="alert">{error}</p>}
        <div className="form-actions">
          <button type="button" onClick={handleAccept} disabled={saving}>
            I understand
          </button>
        </div>
      </div>
    </main>
  );
}
