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
export type DocumentRead = Schemas["DocumentRead"];
export type DocumentDetailRead = Schemas["DocumentDetailRead"];
export type VersionRead = Schemas["VersionRead"];

/** The `params` for endpoints inside an organization. */
export function inOrganization(organizationId: string) {
  return { header: { "X-Organization-Id": organizationId } };
}

export type ErrorBody = {
  error?: { code?: string; message?: string; details?: Record<string, unknown>[] };
};

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: Record<string, unknown>[] = [],
  ) {
    super(message);
  }
}

/** ApiError from an error body of the API (or a generic one when there is no body). */
export function apiError(status: number, body: unknown): ApiError {
  const error = (body as ErrorBody | null | undefined)?.error;
  return new ApiError(
    status,
    error?.code ?? "unknown_error",
    error?.message ?? "No se pudo completar la operación",
    error?.details ?? [],
  );
}

/** Turn an openapi-fetch result into data, or throw ApiError with the API's Spanish message. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error !== undefined || !result.response.ok) {
    throw apiError(result.response.status, result.error);
  }
  return result.data as T;
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "No se pudo conectar con el servidor";
}
