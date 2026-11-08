/**
 * Documents in the browser: upload with progress, download through the API, and labels.
 *
 * Uploads use XMLHttpRequest instead of fetch: fetch cannot report how much of the body was
 * sent yet, and the progress bar needs exactly that.
 */

import { api, apiError, ApiError, inOrganization, type DocumentRead, type Role } from "@/lib/api/client";
import { session as defaultSession, type SessionStore } from "@/lib/api/session";

export const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".txt", ".md"];
export const ACCEPT_ATTRIBUTE = ACCEPTED_EXTENSIONS.join(",");
export const MAX_UPLOAD_MB = 25;

export const KIND_LABELS: Record<string, string> = {
  pdf: "PDF",
  docx: "Word",
  txt: "Texto",
  md: "Markdown",
};

export const STATUS_LABELS: Record<string, string> = {
  pending: "Pendiente de procesar",
  processing: "Procesando",
  ready: "Listo",
  failed: "Falló el procesamiento",
};

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toLocaleString("es-AR", { maximumFractionDigits: value < 10 ? 1 : 0 })} ${units[unit]}`;
}

/** Same rules as the API (documents.upload / documents.delete_any): only to show buttons. */
export function canUpload(role: Role): boolean {
  return role !== "viewer";
}

export function canDelete(role: Role, isAuthor: boolean): boolean {
  return role === "owner" || role === "admin" || (role === "member" && isAuthor);
}

/** The id of the existing document when an upload was refused as a duplicate. */
export function duplicateOf(error: unknown): string | null {
  if (!(error instanceof ApiError) || error.code !== "duplicate_document") return null;
  const id = error.details[0]?.document_id;
  return typeof id === "string" ? id : null;
}

type XhrLike = Pick<XMLHttpRequest, "open" | "setRequestHeader" | "send" | "status" | "responseText"> & {
  upload: Pick<XMLHttpRequestUpload, "onprogress">;
  onload: ((this: XMLHttpRequest, event: ProgressEvent) => unknown) | null;
  onerror: ((this: XMLHttpRequest, event: ProgressEvent) => unknown) | null;
};

export type UploadOptions = {
  organizationId: string;
  file: File;
  /** POST target: the documents collection, or a document's versions. */
  path?: string;
  onProgress?: (fraction: number) => void;
  session?: SessionStore;
  createXhr?: () => XhrLike;
};

function parse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export async function uploadDocument({
  organizationId,
  file,
  path = "/api/v1/documents",
  onProgress,
  session = defaultSession,
  createXhr = () => new XMLHttpRequest() as unknown as XhrLike,
}: UploadOptions): Promise<DocumentRead> {
  function send(token: string | null): Promise<{ status: number; body: unknown }> {
    return new Promise((resolve, reject) => {
      const xhr = createXhr();
      xhr.open("POST", path);
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      xhr.setRequestHeader("X-Organization-Id", organizationId);
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) onProgress?.(event.loaded / event.total);
      };
      xhr.onload = () => resolve({ status: xhr.status, body: parse(xhr.responseText) });
      xhr.onerror = () => reject(new ApiError(0, "network_error", "No se pudo conectar con el servidor"));
      const form = new FormData();
      form.append("file", file);
      xhr.send(form);
    });
  }

  let result = await send(session.token);
  if (result.status === 401) {
    // Same rule as authFetch: renew the session once and try again.
    const token = await session.refresh();
    if (token) {
      onProgress?.(0);
      result = await send(token);
    }
  }
  if (result.status >= 200 && result.status < 300) return result.body as DocumentRead;
  throw apiError(result.status, result.body);
}

/** Download through the API (with the session) and hand the file to the browser. */
export async function downloadDocument(
  organizationId: string,
  documentId: string,
  filename: string,
  version?: number,
): Promise<void> {
  const { data, error, response } = await api.GET("/api/v1/documents/{document_id}/download", {
    params: {
      ...inOrganization(organizationId),
      path: { document_id: documentId },
      query: version ? { version } : {},
    },
    parseAs: "blob",
  });
  if (error !== undefined || !response.ok || !(data instanceof Blob)) {
    throw apiError(response.status, error);
  }
  const url = URL.createObjectURL(data);
  try {
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.append(link);
    link.click();
    link.remove();
  } finally {
    // Give the browser a moment to start the download before releasing the memory.
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  }
}
