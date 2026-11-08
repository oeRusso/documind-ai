"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useSyncExternalStore } from "react";

import { api, unwrap, type OrganizationRead } from "@/lib/api/client";
import {
  getActiveOrganizationId,
  setActiveOrganizationId,
  subscribeActiveOrganization,
} from "@/lib/api/organization-store";
import { useAuth } from "@/lib/auth";

export const ORGANIZATIONS_KEY = ["organizations"] as const;

export function useOrganizations() {
  const { status } = useAuth();
  return useQuery({
    queryKey: ORGANIZATIONS_KEY,
    queryFn: async () => unwrap(await api.GET("/api/v1/organizations")).items,
    enabled: status === "authenticated",
  });
}

/**
 * The organization the user is working in, with their role there. Falls back to the first one
 * when nothing was chosen yet (or the chosen one is gone, e.g. they were removed).
 */
export function useActiveOrganization(): {
  organization: OrganizationRead | null;
  organizations: OrganizationRead[];
  isLoading: boolean;
  select: (id: string) => void;
} {
  const query = useOrganizations();
  const storedId = useSyncExternalStore(
    subscribeActiveOrganization,
    getActiveOrganizationId,
    () => null,
  );
  const organizations = query.data ?? [];
  const organization =
    organizations.find((o) => o.id === storedId) ?? organizations[0] ?? null;

  useEffect(() => {
    // Keep the X-Organization-Id that requests send in line with what the screen shows.
    if (organization && organization.id !== storedId) setActiveOrganizationId(organization.id);
  }, [organization, storedId]);

  return {
    organization: organization && organization.id === storedId ? organization : null,
    organizations,
    isLoading: query.isLoading,
    select: setActiveOrganizationId,
  };
}
