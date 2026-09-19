import { describe, expect, it, vi } from "vitest";

import ReviewProjectPage from "./page";

const mockRedirect = vi.fn();
vi.mock("next/navigation", () => ({
  redirect: (path: string) => mockRedirect(path),
}));

describe("ReviewProjectPage", () => {
  it("sends the bare project URL to the Criteria section", async () => {
    await ReviewProjectPage({ params: Promise.resolve({ id: "7" }) });

    expect(mockRedirect).toHaveBeenCalledWith("/review-projects/7/criteria");
  });
});
