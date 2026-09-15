"use client";

import { type FormEvent, useState } from "react";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { loginReviewer } from "@/lib/api";
import { storeToken } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    try {
      const token = await loginReviewer({ email, password });
      storeToken(token.access_token);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to log in");
    }
  }

  return (
    <main>
      <h1>Log in</h1>
      {error && <p role="alert">{error}</p>}
      <form onSubmit={handleSubmit}>
        <label htmlFor="email">Email</label>
        <input
          id="email"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        <button type="submit">Log in</button>
      </form>
      <p>
        Need an account? <Link href="/register">Register</Link>
      </p>
    </main>
  );
}
