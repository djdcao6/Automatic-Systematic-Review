import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectRail } from "./ProjectRail";

let mockSegment: string | null = null;
vi.mock("next/navigation", () => ({
  useSelectedLayoutSegment: () => mockSegment,
}));

function linkNames(): (string | null)[] {
  const nav = screen.getByRole("navigation", { name: "Project" });
  return within(nav)
    .getAllByRole("link")
    .map((link) => link.textContent);
}

describe("ProjectRail", () => {
  beforeEach(() => {
    mockSegment = null;
  });

  it("links a Solo project to its sections, without the Dual-only ones", () => {
    render(<ProjectRail reviewProjectId="7" reviewMode="solo" isOwner />);

    expect(linkNames()).toEqual([
      "Criteria",
      "Search terms",
      "Citations",
      "Duplicates",
      "Extraction fields",
      "PRISMA flow",
    ]);
    expect(screen.getByRole("link", { name: "Criteria" })).toHaveAttribute(
      "href",
      "/review-projects/7/criteria"
    );
    expect(screen.getByRole("link", { name: "PRISMA flow" })).toHaveAttribute(
      "href",
      "/review-projects/7/flow-diagram"
    );
  });

  it("gives the Owner of a Dual project Conflicts and Invitations too", () => {
    render(<ProjectRail reviewProjectId="7" reviewMode="dual" isOwner />);

    expect(linkNames()).toEqual([
      "Criteria",
      "Search terms",
      "Citations",
      "Duplicates",
      "Conflicts",
      "Extraction fields",
      "PRISMA flow",
      "Invitations",
    ]);
  });

  it("marks only the current section, and keeps Citations current on a citation's own page", () => {
    // Under /review-projects/[id]/citations/[citationId] the layout still sees "citations".
    mockSegment = "citations";
    render(<ProjectRail reviewProjectId="7" reviewMode="solo" isOwner />);

    expect(screen.getByRole("link", { name: "Citations" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Criteria" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: "PRISMA flow" })).not.toHaveAttribute("aria-current");
  });

  it("shows a Co-Reviewer Conflicts but never Invitations", () => {
    render(<ProjectRail reviewProjectId="7" reviewMode="dual" isOwner={false} />);

    expect(linkNames()).toEqual([
      "Criteria",
      "Search terms",
      "Citations",
      "Duplicates",
      "Conflicts",
      "Extraction fields",
      "PRISMA flow",
    ]);
  });

  it("opens and closes the links from a Menu button that controls the navigation", () => {
    render(<ProjectRail reviewProjectId="7" reviewMode="solo" isOwner />);
    const menu = screen.getByRole("button", { name: "Menu" });
    const nav = screen.getByRole("navigation", { name: "Project" });

    expect(menu).toHaveAttribute("aria-expanded", "false");
    expect(menu).toHaveAttribute("aria-controls", nav.id);

    fireEvent.click(menu);
    expect(menu).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(menu);
    expect(menu).toHaveAttribute("aria-expanded", "false");
  });

  it("closes the open menu on Escape and puts focus back on the Menu button", () => {
    render(<ProjectRail reviewProjectId="7" reviewMode="solo" isOwner />);
    const menu = screen.getByRole("button", { name: "Menu" });
    fireEvent.click(menu);
    const firstLink = screen.getByRole("link", { name: "Criteria" });
    firstLink.focus();

    fireEvent.keyDown(firstLink, { key: "Escape" });

    expect(menu).toHaveAttribute("aria-expanded", "false");
    expect(menu).toHaveFocus();
  });

  it("closes the open menu once a link is followed", () => {
    render(<ProjectRail reviewProjectId="7" reviewMode="solo" isOwner />);
    const menu = screen.getByRole("button", { name: "Menu" });
    fireEvent.click(menu);

    fireEvent.click(screen.getByRole("link", { name: "Search terms" }));

    expect(menu).toHaveAttribute("aria-expanded", "false");
  });
});
