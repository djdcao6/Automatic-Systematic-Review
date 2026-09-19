"use client";

import { useEffect, useRef } from "react";

// Keys are a lower-case letter ("i") or "mod+enter" for Ctrl/Cmd+Enter.
type Bindings = Partial<Record<string, () => void>>;

// Letters typed into a field are text, not shortcuts. Radios and checkboxes are
// excluded from that rule so choosing a decision does not trap the keys.
const TEXT_ENTRY =
  "input:not([type='radio']):not([type='checkbox']), textarea, select, [contenteditable]:not([contenteditable='false'])";

function isTextEntry(target: EventTarget | null): boolean {
  return target instanceof Element && target.closest(TEXT_ENTRY) !== null;
}

export function useScreeningShortcuts(bindings: Bindings): void {
  const latest = useRef(bindings);
  useEffect(() => {
    latest.current = bindings;
  });

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const modifier = event.ctrlKey || event.metaKey;

      if (modifier && !event.altKey && event.key === "Enter") {
        const record = latest.current["mod+enter"];
        if (record) {
          event.preventDefault();
          record();
        }
        return;
      }

      if (modifier || event.altKey || isTextEntry(event.target)) return;

      const handler = latest.current[event.key.toLowerCase()];
      if (handler) {
        event.preventDefault();
        handler();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);
}
