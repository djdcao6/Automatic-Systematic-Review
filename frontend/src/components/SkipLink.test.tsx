import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SkipLink } from "./SkipLink";

describe("SkipLink", () => {
  it("moves focus to the page's main landmark", () => {
    render(
      <>
        <SkipLink />
        <nav aria-label="Project">
          <a href="/somewhere">Somewhere</a>
        </nav>
        <main>Content</main>
      </>,
    );

    fireEvent.click(screen.getByRole("link", { name: /skip to main content/i }));

    expect(screen.getByRole("main")).toHaveFocus();
  });

  it("is the first focusable thing on the page", () => {
    render(
      <>
        <SkipLink />
        <a href="/x">Other</a>
      </>,
    );

    expect(screen.getAllByRole("link")[0]).toHaveTextContent(/skip to main content/i);
  });
});
