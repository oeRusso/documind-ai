"use client";

import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";

/** Whether new companies can sign up (REGISTRATION_OPEN on the server). `undefined` while loading:
 * callers hide the sign-up link until they know, so it never flashes on a closed server. */
export function useRegistrationOpen(): boolean | undefined {
  const query = useQuery({
    queryKey: ["registration-status"],
    queryFn: async () => unwrap(await api.GET("/api/v1/auth/registration")),
    staleTime: Infinity,
    retry: false,
  });
  return query.data?.open;
}
