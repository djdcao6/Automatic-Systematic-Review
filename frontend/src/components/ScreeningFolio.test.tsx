import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ScreeningFolio } from "./ScreeningFolio";

const baseProps = {
  position: 412,
  total: 1860,
  decided: 411,
  modeNote: "Dual review",
  previousHref: "/review-projects/1/citations/c411",
  nextHref: "/review-projects/1/citations/c413",
};

// Stop Next's Link from trying to navigate; record where it was headed instead.
function captureNavigation() {
  const visited: string[] = [];
  const onClick = (event: Event) => {
    const link = (event.target as Element).closest("a");
    if (link) visited.push(link.getAttribute("href") ?? "");
    event.preventDefault();
  };
  document.addEventListener("click", onClick, true);
  return { visited, stop: () => document.removeEventListener("click", onClick, true) };
}

describe("ScreeningFolio", () => {
  let navigation: ReturnType<typeof captureNavigation> | null = null;
  afterEach(() => navigation?.stop());

  it("shows the citation's place in the list with a thousands separator", () => {
    render(<ScreeningFolio {...baseProps} />);

    expect(screen.getByText("412")).toBeInTheDocument();
    expect(screen.getByText("of 1,860")).toBeInTheDocument();
    expect(screen.getByText("Dual review")).toBeInTheDocument();
  });

  it("reports how many citations are decided as a progress bar", () => {
    render(<ScreeningFolio {...baseProps} />);

    const bar = screen.getByRole("progressbar", { name: /screening progress/i });
    expect(bar).toHaveAttribute("aria-valuenow", "411");
    expect(bar).toHaveAttribute("aria-valuemax", "1860");
    expect(bar).toHaveAttribute("aria-valuetext", "411 of 1,860 decided");
  });

  it("links to the previous and next citations", () => {
    render(<ScreeningFolio {...baseProps} />);

    expect(screen.getByRole("link", { name: "Previous" })).toHaveAttribute(
      "href",
      "/review-projects/1/citations/c411"
    );
    expect(screen.getByRole("link", { name: "Next" })).toHaveAttribute(
      "href",
      "/review-projects/1/citations/c413"
    );
  });

  it("shows an inert control, not a link, at either end of the list", () => {
    render(<ScreeningFolio {...baseProps} previousHref={null} nextHref={null} />);

    expect(screen.queryByRole("link", { name: "Previous" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Next" })).not.toBeInTheDocument();
    expect(screen.getByText("Previous").closest("[aria-disabled]")).toHaveAttribute(
      "aria-disabled",
      "true"
    );
    expect(screen.getByText("Next").closest("[aria-disabled]")).toHaveAttribute(
      "aria-disabled",
      "true"
    );
  });

  it("advertises the J and K keys", () => {
    render(<ScreeningFolio {...baseProps} />);

    expect(screen.getByRole("link", { name: "Previous" })).toHaveAttribute(
      "aria-keyshortcuts",
      "k"
    );
    expect(screen.getByRole("link", { name: "Next" })).toHaveAttribute("aria-keyshortcuts", "j");
  });

  it("follows the next and previous links on J and K", () => {
    navigation = captureNavigation();
    render(<ScreeningFolio {...baseProps} />);

    fireEvent.keyDown(document.body, { key: "j" });
    fireEvent.keyDown(document.body, { key: "k" });

    expect(navigation.visited).toEqual([
      "/review-projects/1/citations/c413",
      "/review-projects/1/citations/c411",
    ]);
  });

  it("does nothing on J or K where there is no neighbour", () => {
    navigation = captureNavigation();
    const spy = vi.fn();
    render(<ScreeningFolio {...baseProps} previousHref={null} nextHref={null} />);
    document.addEventListener("click", spy, true);

    fireEvent.keyDown(document.body, { key: "j" });
    fireEvent.keyDown(document.body, { key: "k" });
    document.removeEventListener("click", spy, true);

    expect(spy).not.toHaveBeenCalled();
  });
});
