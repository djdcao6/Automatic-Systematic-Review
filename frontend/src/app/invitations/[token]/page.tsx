"use client";

import { type FormEvent, useEffect, useState } from "react";

import { useRouter } from "next/navigation";

import {
  acceptInvitationByLoggingIn,
  acceptInvitationByRegistering,
  getInvitationPublic,
  type InvitationPublic,
} from "@/lib/api";
import { storeToken } from "@/lib/auth";

export default function AcceptInvitationPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [invitation, setInvitation] = useState<InvitationPublic | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [registerEmail, setRegisterEmail] = useState("");
  const [registerPassword, setRegisterPassword] = useState("");
  const [registerError, setRegisterError] = useState<string | null>(null);

  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [loginError, setLoginError] = useState<string | null>(null);

  useEffect(() => {
    params.then((resolved) => setToken(resolved.token));
  }, [params]);

  useEffect(() => {
    if (!token) return;
    getInvitationPublic(token)
      .then(setInvitation)
      .catch((err) =>
        setLoadError(err instanceof Error ? err.message : "Failed to load invitation")
      );
  }, [token]);

  async function handleRegister(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    setRegisterError(null);
    try {
      const result = await acceptInvitationByRegistering(token, {
        email: registerEmail,
        password: registerPassword,
      });
      storeToken(result.access_token);
      router.push(`/review-projects/${result.review_project_id}`);
    } catch (err) {
      setRegisterError(err instanceof Error ? err.message : "Failed to accept invitation");
    }
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    setLoginError(null);
    try {
      const result = await acceptInvitationByLoggingIn(token, {
        email: loginEmail,
        password: loginPassword,
      });
      storeToken(result.access_token);
      router.push(`/review-projects/${result.review_project_id}`);
    } catch (err) {
      setLoginError(err instanceof Error ? err.message : "Failed to accept invitation");
    }
  }

  if (loadError) {
    return (
      <main>
        <h1>Invitation</h1>
        <p role="alert">{loadError}</p>
      </main>
    );
  }

  if (!invitation) {
    return (
      <main>
        <h1>Invitation</h1>
        <p>Loading...</p>
      </main>
    );
  }

  if (invitation.status !== "pending") {
    return (
      <main>
        <h1>Invitation</h1>
        <p role="alert">This invitation is no longer valid.</p>
      </main>
    );
  }

  return (
    <main>
      <h1>Join &quot;{invitation.review_project_name}&quot; as Co-Reviewer</h1>

      <section>
        <h2>Register</h2>
        {registerError && <p role="alert">{registerError}</p>}
        <form onSubmit={handleRegister}>
          <label htmlFor="register-email">Email</label>
          <input
            id="register-email"
            type="email"
            value={registerEmail}
            onChange={(event) => setRegisterEmail(event.target.value)}
          />
          <label htmlFor="register-password">Password</label>
          <input
            id="register-password"
            type="password"
            value={registerPassword}
            onChange={(event) => setRegisterPassword(event.target.value)}
          />
          <button type="submit">Register &amp; Join</button>
        </form>
      </section>

      <section>
        <h2>Log in</h2>
        {loginError && <p role="alert">{loginError}</p>}
        <form onSubmit={handleLogin}>
          <label htmlFor="login-email">Email</label>
          <input
            id="login-email"
            type="email"
            value={loginEmail}
            onChange={(event) => setLoginEmail(event.target.value)}
          />
          <label htmlFor="login-password">Password</label>
          <input
            id="login-password"
            type="password"
            value={loginPassword}
            onChange={(event) => setLoginPassword(event.target.value)}
          />
          <button type="submit">Log in &amp; Join</button>
        </form>
      </section>
    </main>
  );
}
