"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { PageStatus } from "@/components/PageStatus";
import {
  createCheckoutSession,
  createPortalSession,
  getMySubscription,
  type Subscription,
} from "@/lib/api";

export default function AccountPage() {
  const [subscription, setSubscription] = useState<Subscription | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMySubscription()
      .then(setSubscription)
      .catch(() => setError("Failed to load your subscription."));
  }, []);

  async function handleUpgrade() {
    try {
      const { url } = await createCheckoutSession();
      window.location.href = url;
    } catch {
      setError("Failed to start checkout.");
    }
  }

  async function handleManageSubscription() {
    try {
      const { url } = await createPortalSession();
      window.location.href = url;
    } catch {
      setError("Failed to open billing portal.");
    }
  }

  if (subscription === undefined) {
    return <PageStatus error={error} />;
  }

  if (subscription === null) {
    return <PageStatus error="Billing is not available." />;
  }

  return (
    <main className="page">
      <Link href="/" className="crumb">Back to Review Projects</Link>
      <h1>Account / Billing</h1>
      {error && <p role="alert">{error}</p>}
      <p>Plan: {subscription.plan === "paid" ? "Paid" : "Free"}</p>
      {subscription.plan === "free" && (
        <button type="button" onClick={handleUpgrade}>
          Upgrade
        </button>
      )}
      {subscription.plan === "paid" && (
        <button type="button" onClick={handleManageSubscription}>
          Manage subscription
        </button>
      )}
    </main>
  );
}
