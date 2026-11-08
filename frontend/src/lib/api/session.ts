/**
 * The session in the browser (ADR 0004).
 *
 * - The access token lives only in memory (this object): JavaScript injected by an XSS cannot
 *   find it in localStorage, and a reload simply asks for a new one.
 * - The refresh token is an HttpOnly cookie: this code never sees it. To renew, it calls
 *   /auth/refresh and repeats the `csrf_token` cookie in the X-CSRF-Token header.
 * - Single flight: if several requests need a new token at once, only ONE refresh is sent and
 *   all of them wait for it. Two refreshes with the same cookie would look like a stolen token
 *   being reused, and the API would close the session.
 */

export const REFRESH_PATH = "/api/v1/auth/refresh";
export const CSRF_COOKIE = "csrf_token";
export const CSRF_HEADER = "X-CSRF-Token";

type FetchLike = (input: string, init: RequestInit) => Promise<Response>;

export function readCookie(name: string, cookies: string = document.cookie): string | null {
  for (const part of cookies.split(";")) {
    const [key, ...value] = part.trim().split("=");
    if (key === name) return decodeURIComponent(value.join("="));
  }
  return null;
}

export class SessionStore {
  private accessToken: string | null = null;
  private refreshing: Promise<string | null> | null = null;

  constructor(
    private readonly fetchImpl: FetchLike = (input, init) => fetch(input, init),
    private readonly cookies: () => string = () => document.cookie,
  ) {}

  get token(): string | null {
    return this.accessToken;
  }

  setToken(token: string | null): void {
    this.accessToken = token;
  }

  csrfToken(): string | null {
    return readCookie(CSRF_COOKIE, this.cookies());
  }

  /** A new access token, or null when there is no valid session (then: go to /login). */
  refresh(): Promise<string | null> {
    this.refreshing ??= this.doRefresh().finally(() => {
      this.refreshing = null;
    });
    return this.refreshing;
  }

  private async doRefresh(): Promise<string | null> {
    const csrf = this.csrfToken();
    if (!csrf) {
      this.accessToken = null; // never logged in on this browser (or logged out)
      return null;
    }
    try {
      const response = await this.fetchImpl(REFRESH_PATH, {
        method: "POST",
        credentials: "same-origin",
        headers: { [CSRF_HEADER]: csrf },
      });
      if (!response.ok) {
        this.accessToken = null;
        return null;
      }
      const body = (await response.json()) as { access_token: string };
      this.accessToken = body.access_token;
      return this.accessToken;
    } catch {
      this.accessToken = null;
      return null;
    }
  }
}

export const session = new SessionStore();
