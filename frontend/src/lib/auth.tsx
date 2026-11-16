"use client";

/**
 * Who is logged in, for the whole app. On load it tries to renew the session from the cookie
 * (the access token is not kept across reloads, ADR 0004).
 */

import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api, unwrap } from "@/lib/api/client";
import { setActiveOrganizationId } from "@/lib/api/organization-store";
import { CSRF_HEADER, session } from "@/lib/api/session";

export type CurrentUser = { id: string; email: string };
type Status = "loading" | "anonymous" | "authenticated";

type AuthContextValue = {
  status: Status;
  user: CurrentUser | null;
  /** After login, register or a refresh: keep the token and load the user. */
  startSession: (accessToken: string) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<Status>("loading");
  const [user, setUser] = useState<CurrentUser | null>(null);

  const loadUser = useCallback(async () => {
    try {
      const me = unwrap(await api.GET("/api/v1/auth/me"));
      setUser({ id: me.id, email: me.email });
      setStatus("authenticated");
    } catch {
      session.setToken(null);
      setUser(null);
      setStatus("anonymous");
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const token = session.token ?? (await session.refresh());
      if (cancelled) return;
      if (token) await loadUser();
      else setStatus("anonymous");
    })();
    return () => {
      cancelled = true;
    };
  }, [loadUser]);

  const startSession = useCallback(
    async (accessToken: string) => {
      session.setToken(accessToken);
      queryClient.clear(); // nothing from a previous user survives
      await loadUser();
    },
    [loadUser, queryClient],
  );

  const logout = useCallback(async () => {
    const csrf = session.csrfToken();
    await api.POST("/api/v1/auth/logout", {
      headers: csrf ? { [CSRF_HEADER]: csrf } : {},
    });
    session.setToken(null);
    setActiveOrganizationId(null);
    queryClient.clear();
    setUser(null);
    setStatus("anonymous");
  }, [queryClient]);

  const value = useMemo(
    () => ({ status, user, startSession, logout }),
    [status, user, startSession, logout],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}

/** Only internal paths: "?next=https://evil.example" must not send people away. */
export function safeNextPath(next: string | null, fallback = "/documents"): string {
  if (!next || !next.startsWith("/") || next.startsWith("//")) return fallback;
  return next;
}
