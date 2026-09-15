import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as auth from "@/lib/auth";

vi.mock("@/lib/auth");

const mockedAuth = vi.mocked(auth);

import { listReviewProjects, loginReviewer, registerReviewer } from "@/lib/api";

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
});
