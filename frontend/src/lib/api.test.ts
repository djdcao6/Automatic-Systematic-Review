import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as auth from "@/lib/auth";

vi.mock("@/lib/auth");

const mockedAuth = vi.mocked(auth);

import {
  createExtractionField,
  createReviewProject,
  dismissPossibleDuplicate,
  ExtractionFieldNameTakenError,
  getMySubscription,
  getReviewProject,
  listReviewProjects,
  loginReviewer,
  registerReviewer,
  ReviewProjectCapError,
  updateExtractionField,
} from "@/lib/api";

function stubLocation() {
  Object.defineProperty(window, "location", {
    value: { href: "" },
    writable: true,
    configurable: true,
  });
}

describe("api authorization handling", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    mockedAuth.getToken.mockReturnValue("test-token");
    stubLocation();
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("attaches the stored token as a Bearer Authorization header", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));
    global.fetch = fetchMock;

    await listReviewProjects();

    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Headers).get("Authorization")).toBe("Bearer test-token");
  });

  it("sends no Authorization header when there is no stored token", async () => {
    mockedAuth.getToken.mockReturnValue(null);
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));
    global.fetch = fetchMock;

    await listReviewProjects();

    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Headers).has("Authorization")).toBe(false);
  });

  it("does not attach an Authorization header to register or login", async () => {
    const fetchMock = vi.fn().mockImplementation(
      async () =>
        new Response(JSON.stringify({ access_token: "t", token_type: "bearer" }), {
          status: 200,
        })
    );
    global.fetch = fetchMock;

    await loginReviewer({ email: "a@example.com", password: "correcthorse" });
    await registerReviewer({ email: "a@example.com", password: "correcthorse" });

    for (const [, init] of fetchMock.mock.calls) {
      expect((init.headers as Record<string, string>)["Authorization"]).toBeUndefined();
    }
  });

  it("clears the token and routes to /login on a 401 response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 401 }));
    global.fetch = fetchMock;

    await expect(listReviewProjects()).rejects.toThrow();

    expect(mockedAuth.clearToken).toHaveBeenCalled();
    expect(window.location.href).toBe("/login");
  });

  it("does not clear the token or redirect on a successful response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }));
    global.fetch = fetchMock;

    await listReviewProjects();

    expect(mockedAuth.clearToken).not.toHaveBeenCalled();
    expect(window.location.href).toBe("");
  });

  it("does not redirect on an expired-login 401, only on a gated endpoint's 401", async () => {
    // A wrong-password /login response is also a 401, but callers of
    // loginReviewer (the login form) show that inline rather than redirecting,
    // since register/login use plain fetch, not the authorizedFetch wrapper.
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Incorrect email or password" }), { status: 401 })
    );
    global.fetch = fetchMock;

    await expect(
      loginReviewer({ email: "a@example.com", password: "wrong" })
    ).rejects.toThrow("Incorrect email or password");

    expect(mockedAuth.clearToken).not.toHaveBeenCalled();
    expect(window.location.href).toBe("");
  });

  it("throws a ReviewProjectCapError carrying the backend's message on a 403 (#41)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: "Free Plan is limited to 1 Review Project. Upgrade to create more.",
        }),
        { status: 403 }
      )
    );
    global.fetch = fetchMock;

    const error: unknown = await createReviewProject({
      name: "Second Review",
      merge_mode: "combine",
      review_mode: "solo",
    }).catch((caught) => caught);

    expect(error).toBeInstanceOf(ReviewProjectCapError);
    expect((error as Error).message).toBe(
      "Free Plan is limited to 1 Review Project. Upgrade to create more."
    );
  });

  it("throws an ExtractionFieldNameTakenError carrying the backend's message on a 409 (#67)", async () => {
    const detail =
      'An active Extraction Field named "Sample size" already exists in this Review Project';
    const fetchMock = vi
      .fn()
      .mockImplementation(async () => new Response(JSON.stringify({ detail }), { status: 409 }));
    global.fetch = fetchMock;

    const created: unknown = await createExtractionField("proj-1", {
      name: "Sample size",
      description: null,
    }).catch((caught) => caught);
    const renamed: unknown = await updateExtractionField("proj-1", "f1", {
      name: "Sample size",
      description: null,
    }).catch((caught) => caught);

    for (const error of [created, renamed]) {
      expect(error).toBeInstanceOf(ExtractionFieldNameTakenError);
      expect((error as Error).message).toBe(detail);
    }
  });

  it("keeps a plain Error for other extraction-field failures", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ detail: "boom" }), { status: 500 }));
    global.fetch = fetchMock;

    const error: unknown = await createExtractionField("proj-1", {
      name: "Sample size",
      description: null,
    }).catch((caught) => caught);

    expect(error).not.toBeInstanceOf(ExtractionFieldNameTakenError);
    expect((error as Error).message).toBe("boom");
  });

  it("surfaces the backend's real detail even for endpoints that used to throw a generic string", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ detail: "Review project belongs to a different Reviewer" }),
        { status: 403 }
      )
    );
    global.fetch = fetchMock;

    await expect(getReviewProject("proj-1")).rejects.toThrow(
      "Review project belongs to a different Reviewer"
    );
  });

  // Regression: ISSUE-001 — a 422 validation error's `detail` is a list of
  // { loc, msg } objects, not a string, so register with a too-short password
  // showed only "Failed to register".
  // Found by /qa on 2026-09-19
  // Report: .gstack/qa-reports/qa-report-localhost-2026-09-19.md
  it("surfaces field-level messages from a 422 validation error's detail list", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: [
            {
              type: "string_too_short",
              loc: ["body", "password"],
              msg: "String should have at least 8 characters",
            },
          ],
        }),
        { status: 422 }
      )
    );
    global.fetch = fetchMock;

    await expect(registerReviewer({ email: "a@b.co", password: "short" })).rejects.toThrow(
      "password: String should have at least 8 characters"
    );
  });

  it("joins every field's message when a 422 reports several problems", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: [
            { loc: ["body", "email"], msg: "value is not a valid email address" },
            { loc: ["body", "password"], msg: "String should have at least 8 characters" },
          ],
        }),
        { status: 422 }
      )
    );
    global.fetch = fetchMock;

    await expect(registerReviewer({ email: "nope", password: "x" })).rejects.toThrow(
      "email: value is not a valid email address; password: String should have at least 8 characters"
    );
  });

  it("falls back to the generic message when a detail list has no usable messages", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ detail: [{}] }), { status: 422 }));
    global.fetch = fetchMock;

    await expect(registerReviewer({ email: "a@b.co", password: "x" })).rejects.toThrow(
      "Failed to register"
    );
  });

  it("falls back to a generic message when the backend response has no detail", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 500 }));
    global.fetch = fetchMock;

    await expect(getReviewProject("proj-1")).rejects.toThrow("Failed to load review project");
  });

  it("surfaces real detail for void-returning endpoints too", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Possible duplicate already resolved" }), {
        status: 409,
      })
    );
    global.fetch = fetchMock;

    await expect(dismissPossibleDuplicate("proj-1", "dup-1")).rejects.toThrow(
      "Possible duplicate already resolved"
    );
  });

  it("still returns null for a 404 on getMySubscription rather than throwing", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 404 }));
    global.fetch = fetchMock;

    await expect(getMySubscription()).resolves.toBeNull();
  });
});
