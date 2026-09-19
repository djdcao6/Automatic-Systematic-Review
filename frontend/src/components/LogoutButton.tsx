"use client";

import { useSyncExternalStore } from "react";

import { usePathname, useRouter } from "next/navigation";

import { clearToken, getToken } from "@/lib/auth";

// localStorage doesn't notify the tab that wrote to it, so logging out here
// tells our own subscribers directly; the `storage` event covers other tabs.
const tokenListeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  tokenListeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    tokenListeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

const hasToken = () => getToken() !== null;
const serverHasNoToken = () => false;

export function LogoutButton() {
  const router = useRouter();
  // The root layout never remounts between pages, so reading the pathname
  // re-renders this on every navigation and re-reads the token: logging in
  // (store token, push "/") shows the button, an expired session hides it.
  usePathname();
  const loggedIn = useSyncExternalStore(subscribe, hasToken, serverHasNoToken);

  if (!loggedIn) return null;

  function handleLogout() {
    clearToken();
    tokenListeners.forEach((listener) => listener());
    router.push("/login");
  }

  return (
    <header>
      <button type="button" onClick={handleLogout}>
        Log out
      </button>
    </header>
  );
}
