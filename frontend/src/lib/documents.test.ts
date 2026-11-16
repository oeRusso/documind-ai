import { describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/client";
import { SessionStore } from "@/lib/api/session";

import {
  canDelete,
  canUpload,
  duplicateOf,
  formatBytes,
  isDocumentBusy,
  isProcessingFinal,
  pageRange,
  uploadDocument,
} from "./documents";

/** A scripted XMLHttpRequest: answers each send() with the next status/body. */
function fakeXhrs(answers: { status: number; body: unknown }[]) {
  const sent: { headers: Record<string, string>; path: string }[] = [];
  const create = () => {
    const headers: Record<string, string> = {};
    let path = "";
    const xhr = {
      status: 0,
      responseText: "",
      upload: { onprogress: null as ((event: ProgressEvent) => void) | null },
      onload: null as (() => void) | null,
      onerror: null as (() => void) | null,
      open: (_method: string, url: string) => {
        path = url;
      },
      setRequestHeader: (name: string, value: string) => {
        headers[name] = value;
      },
      send: () => {
        sent.push({ headers, path });
        const answer = answers.shift();
        if (!answer) throw new Error("unexpected request");
        xhr.upload.onprogress?.({ lengthComputable: true, loaded: 50, total: 100 } as ProgressEvent);
        xhr.status = answer.status;
        xhr.responseText = JSON.stringify(answer.body);
        xhr.onload?.();
      },
    };
    return xhr;
  };
  return { create: create as never, sent };
}

function sessionWith(token: string, renewed: string | null = "nuevo") {
  const store = new SessionStore(
    async () => new Response(JSON.stringify({ access_token: renewed }), { status: renewed ? 200 : 401 }),
    () => "csrf_token=abc",
  );
  store.setToken(token);
  return store;
}

const FILE = new File(["hola"], "contrato.pdf");

describe("uploadDocument", () => {
  it("sends the token and the organization, and reports progress", async () => {
    const xhrs = fakeXhrs([{ status: 201, body: { id: "d1" } }]);
    const onProgress = vi.fn();

    const created = await uploadDocument({
      organizationId: "org-1",
      file: FILE,
      onProgress,
      session: sessionWith("viejo"),
      createXhr: xhrs.create,
    });

    expect(created).toEqual({ id: "d1" });
    expect(xhrs.sent[0]?.headers).toEqual({ Authorization: "Bearer viejo", "X-Organization-Id": "org-1" });
    expect(onProgress).toHaveBeenCalledWith(0.5);
  });

  it("renews an expired session once and retries", async () => {
    const xhrs = fakeXhrs([
      { status: 401, body: {} },
      { status: 201, body: { id: "d1" } },
    ]);

    await uploadDocument({ organizationId: "o", file: FILE, session: sessionWith("viejo"), createXhr: xhrs.create });

    expect(xhrs.sent.map((s) => s.headers.Authorization)).toEqual(["Bearer viejo", "Bearer nuevo"]);
  });

  it("turns the API error into an ApiError with its details", async () => {
    const xhrs = fakeXhrs([
      {
        status: 409,
        body: { error: { code: "duplicate_document", message: "Ya está", details: [{ document_id: "d0" }] } },
      },
    ]);

    const error = await uploadDocument({
      organizationId: "o",
      file: FILE,
      session: sessionWith("t"),
      createXhr: xhrs.create,
    }).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toBe("Ya está");
    expect(duplicateOf(error)).toBe("d0");
  });
});

describe("helpers", () => {
  it("formats sizes for people", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1536)).toBe("1,5 KB");
    expect(formatBytes(25 * 1024 * 1024)).toBe("25 MB");
  });

  it("mirrors the API's document permissions", () => {
    expect(canUpload("viewer")).toBe(false);
    expect(canUpload("member")).toBe(true);
    expect(canDelete("member", false)).toBe(false);
    expect(canDelete("member", true)).toBe(true);
    expect(canDelete("admin", false)).toBe(true);
    expect(canDelete("viewer", true)).toBe(false);
  });

  it("only reports duplicates for the duplicate error", () => {
    expect(duplicateOf(new ApiError(415, "unsupported_file_type", "x"))).toBeNull();
    expect(duplicateOf(new Error("x"))).toBeNull();
  });
});

describe("processing helpers", () => {
  it("knows when to stop asking", () => {
    expect(isProcessingFinal("ready")).toBe(true);
    expect(isProcessingFinal("failed")).toBe(true);
    expect(isProcessingFinal(null)).toBe(true); // documents from before stage 5
    expect(isProcessingFinal("ocr")).toBe(false);
    expect(isDocumentBusy("processing")).toBe(true);
    expect(isDocumentBusy("ready")).toBe(false);
  });

  it("writes page ranges", () => {
    expect(pageRange(3, 3)).toBe("pág. 3");
    expect(pageRange(3, 5)).toBe("págs. 3–5");
    expect(pageRange(null, null)).toBeNull();
  });
});
