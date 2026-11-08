import { describe, expect, it, vi } from "vitest";

import { createAuthFetch } from "./auth-fetch";
import { SessionStore } from "./session";

const API = "http://localhost/api/v1";

function storeWith(token: string | null, refreshed: string | null): SessionStore {
  const store = new SessionStore(vi.fn(), () => "");
  store.setToken(token);
  vi.spyOn(store, "refresh").mockImplementation(async () => {
    store.setToken(refreshed);
    return refreshed;
  });
  return store;
}

const status = (code: number) => new Response(null, { status: code });

describe("createAuthFetch", () => {
  it("adds the access token", async () => {
    const base = vi.fn<(request: Request) => Promise<Response>>(async () => status(200));
    const authFetch = createAuthFetch(storeWith("t1", null), base);

    await authFetch(new Request(`${API}/auth/me`));

    expect(base.mock.calls[0]?.[0].headers.get("Authorization")).toBe("Bearer t1");
  });

  it("on 401 renews the session and repeats the request once, body included", async () => {
    const base = vi.fn(async (request: Request) =>
      request.headers.get("Authorization") === "Bearer fresh" ? status(201) : status(401),
    );
    const store = storeWith("expired", "fresh");
    const authFetch = createAuthFetch(store, base);

    const response = await authFetch(
      new Request(`${API}/invitations`, { method: "POST", body: JSON.stringify({ email: "a@b.co" }) }),
    );

    expect(response.status).toBe(201);
    expect(store.refresh).toHaveBeenCalledTimes(1);
    expect(base).toHaveBeenCalledTimes(2);
    await expect(base.mock.calls[1]?.[0].json()).resolves.toEqual({ email: "a@b.co" });
  });

  it("returns the 401 when the session cannot be renewed", async () => {
    const authFetch = createAuthFetch(storeWith("expired", null), async () => status(401));

    expect((await authFetch(new Request(`${API}/members`))).status).toBe(401);
  });

  it("does not renew after a failed login (wrong password is not an expired token)", async () => {
    const store = storeWith(null, "never");
    const authFetch = createAuthFetch(store, async () => status(401));

    await authFetch(new Request(`${API}/auth/login`, { method: "POST", body: "{}" }));

    expect(store.refresh).not.toHaveBeenCalled();
  });

  it("other errors pass through untouched", async () => {
    const store = storeWith("t", "x");
    const authFetch = createAuthFetch(store, async () => status(403));

    expect((await authFetch(new Request(`${API}/members`))).status).toBe(403);
    expect(store.refresh).not.toHaveBeenCalled();
  });
});
