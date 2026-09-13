import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Home from "./page";

describe("Home", () => {
  it("renders", () => {
    render(<Home />);
    expect(screen.getByText(/page.tsx/i)).toBeInTheDocument();
  });
});
