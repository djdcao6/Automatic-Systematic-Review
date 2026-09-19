import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PageStatus } from "./PageStatus";

describe("PageStatus", () => {
  it("says Loading... inside the page's main", () => {
    render(<PageStatus />);

    expect(screen.getByRole("main")).toHaveTextContent("Loading...");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows an error as an alert inside main, and stops saying it is loading", () => {
    render(<PageStatus error="Failed to load it." />);

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Failed to load it.");
    expect(screen.getByRole("main")).toContainElement(alert);
    expect(screen.queryByText("Loading...")).not.toBeInTheDocument();
  });

  it("uses the same page width as the pages it stands in for", () => {
    render(<PageStatus />);

    expect(screen.getByRole("main")).toHaveClass("page");
  });
});
