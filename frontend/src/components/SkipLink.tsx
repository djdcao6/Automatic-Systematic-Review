"use client";

import type { MouseEvent } from "react";

// Lets keyboard users jump past the top bar (and the project rail) to the page's <main>.
// Every page has one <main>, so this finds it rather than needing an id on each.
export function SkipLink() {
  function handleClick(event: MouseEvent<HTMLAnchorElement>) {
    const main = document.querySelector("main");
    if (!main) return;
    event.preventDefault();
    main.tabIndex = -1;
    main.focus();
  }

  return (
    <a href="#main" className="skip-link" onClick={handleClick}>
      Skip to main content
    </a>
  );
}
