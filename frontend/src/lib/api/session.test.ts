import { describe, expect, it, vi } from "vitest";

import { readCookie, REFRESH_PATH, SessionStore } from "./session";

function okResponse(token: string): Response {
  return new Response(JSON.stringify({ access_token: token }), { status: 200 });
}

describe("readCookie", () => {
  it("finds a cookie among others", () => {
    expect(readCookie("csrf_token", "a=1; csrf_token=abc%3D; b=2")).toBe("abc=");
    expect(readCookie("csrf_token", "a=1")).toBeNull();
  });
});

describe("SessionStore.refresh", () => {
  it("sends the CSRF cookie value in the header", async () => {
    const fetchImpl = vi.fn(async () => okResponse("new-token"));
    const store = new SessionStore(fetchImpl, () => "csrf_token=xyz");

    await expect(store.refresh()).resolves.toBe("new-token");

    expect(fetchImpl).toHaveBeenCalledWith(REFRESH_PATH, {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRF-Token": "xyz" },
    });
    expect(store.token).toBe("new-token");
  });

  it("sends ONE refresh when many requests need it at the same time (single flight)", async () => {
    let release!: (response: Response) => void;
    const fetchImpl = vi.fn(() => new Promise<Response>((resolve) => (release = resolve)));
    const store = new SessionStore(fetchImpl, () => "csrf_token=xyz");

    const waiting = [store.refresh(), store.refresh(), store.refresh()];
    release(okResponse("shared"));

    await expect(Promise.all(waiting)).resolves.toEqual(["shared", "shared", "shared"]);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    // Once finished, a later refresh is a new request.
    fetchImpl.mockImplementation(async () => okResponse("later"));
    await expect(store.refresh()).resolves.toBe("later");
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it("without the CSRF cookie there is no session and no request", async () => {
    const fetchImpl = vi.fn();
    const store = new SessionStore(fetchImpl, () => "");

    await expect(store.refresh()).resolves.toBeNull();
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("a rejected refresh (revoked or expired session) forgets the token", async () => {
    const store = new SessionStore(async () => new Response("{}", { status: 401 }), () => "csrf_token=x");
    store.setToken("old");

    await expect(store.refresh()).resolves.toBeNull();
    expect(store.token).toBeNull();
  });

  it("a network error is treated as no session", async () => {
    const store = new SessionStore(async () => Promise.reject(new TypeError("offline")), () => "csrf_token=x");

    await expect(store.refresh()).resolves.toBeNull();
  });
});
