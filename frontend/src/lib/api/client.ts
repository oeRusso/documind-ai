import createClient from "openapi-fetch";

import { createAuthFetch } from "./auth-fetch";
import type { components, paths } from "./schema";
import { session } from "./session";

/** Typed client generated from the backend's OpenAPI (pnpm gen:api). Browser only. */
export const api = createClient<paths>({
  baseUrl: typeof window === "undefined" ? "http://localhost" : window.location.origin,
  fetch: createAuthFetch(session),
});

export type Schemas = components["schemas"];
export type Role = Schemas["Role"];
export type OrganizationRead = Schemas["OrganizationRead"];
export type MemberRead = Schemas["MemberRead"];
export type InvitationRead = Schemas["InvitationRead"];

/** The `params` for endpoints inside an organization. */
export function inOrganization(organizationId: string) {
  return { header: { "X-Organization-Id": organizationId } };
}

type ErrorBody = { error?: { code?: string; message?: string } };

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

/** Turn an openapi-fetch result into data, or throw ApiError with the API's Spanish message. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error !== undefined || !result.response.ok) {
    const body = (result.error ?? {}) as ErrorBody;
    throw new ApiError(
      result.response.status,
      body.error?.code ?? "unknown_error",
      body.error?.message ?? "No se pudo completar la operación",
    );
  }
  return result.data as T;
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "No se pudo conectar con el servidor";
}
