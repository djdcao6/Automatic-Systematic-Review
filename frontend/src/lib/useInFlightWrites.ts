"use client";

import { useRef, useState } from "react";

// Which writes are in flight, by key. The ref is the guard: it changes the moment a
// write starts, before React re-renders, so a second click or a keyboard shortcut in the
// same tick is turned away. The state is for the screen, so the controls can be disabled.
export function useInFlightWrites() {
  const running = useRef(new Set<string>());
  const [pending, setPending] = useState<ReadonlySet<string>>(new Set());

  function syncPending() {
    setPending(new Set(running.current));
  }

  // Runs `write` unless one with the same key is already in flight, in which case
  // the call is turned away. Whatever `write` does, the key is released afterwards.
  async function run(key: string, write: () => Promise<void>): Promise<void> {
    if (running.current.has(key)) return;
    running.current.add(key);
    syncPending();
    try {
      await write();
    } finally {
      running.current.delete(key);
      syncPending();
    }
  }

  const any = (keys: Iterable<string>, matches: (key: string) => boolean) =>
    [...keys].some(matches);

  return {
    run,
    // Right now, for a handler that must not start another write.
    isRunning: (matches: (key: string) => boolean) => any(running.current, matches),
    // As of the last render, for a control that should look disabled.
    isPending: (matches: (key: string) => boolean) => any(pending, matches),
  };
}
