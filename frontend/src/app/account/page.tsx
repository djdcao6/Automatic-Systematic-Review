"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { createCheckoutSession, getMySubscription, type Subscription } from "@/lib/api";

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

  if (subscription === undefined) {
    return error ? <p role="alert">{error}</p> : <p>Loading...</p>;
  }

  if (subscription === null) {
    return <p role="alert">Billing is not available.</p>;
  }

  return (
    <main>
      <h1>Account / Billing</h1>
      <Link href="/">Back to Review Projects</Link>
      {error && <p role="alert">{error}</p>}
      <p>Plan: {subscription.plan === "paid" ? "Paid" : "Free"}</p>
      {subscription.plan === "free" && (
        <button type="button" onClick={handleUpgrade}>
          Upgrade
        </button>
      )}
    </main>
  );
}
