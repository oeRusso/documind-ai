/**
 * The fetch used by the API client: adds the access token, and when a request gets 401 (token
 * expired), renews the session once and repeats the request. The organization travels in each
 * call's own X-Organization-Id header (the generated types require it).
 */

import type { SessionStore } from "./session";

// A 401 from these means "wrong password" or "no session": renewing would not help.
const NO_RETRY = ["/auth/login", "/auth/register", "/auth/refresh", "/auth/logout"];

export function createAuthFetch(
  session: SessionStore,
  baseFetch: (request: Request) => Promise<Response> = (request) => fetch(request),
): (request: Request) => Promise<Response> {
  function prepare(request: Request, token: string | null): Request {
    const prepared = new Request(request);
    if (token) prepared.headers.set("Authorization", `Bearer ${token}`);
    return prepared;
  }

  return async (request) => {
    const retry = request.clone(); // a body can be read only once: keep a copy for the retry
    const response = await baseFetch(prepare(request, session.token));
    const path = new URL(request.url).pathname;
    if (response.status !== 401 || NO_RETRY.some((p) => path.endsWith(p))) {
      return response;
    }
    const token = await session.refresh();
    if (!token) return response; // the session is over: the caller sends the user to /login
    return baseFetch(prepare(retry, token));
  };
}
