import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/client";

import { DocumentUploader } from "./documents";

const uploadDocument = vi.fn();
vi.mock("@/lib/documents", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/documents")>()),
  uploadDocument: (...args: unknown[]) => uploadDocument(...args),
}));

function pick(name: string) {
  return new File(["contenido"], name, { type: "application/pdf" });
}

describe("DocumentUploader", () => {
  beforeEach(() => {
    uploadDocument.mockReset();
  });

  it("uploads each chosen file and tells the page", async () => {
    uploadDocument.mockResolvedValue({ id: "d1" });
    const onUploaded = vi.fn();
    render(<DocumentUploader organizationId="org-1" onUploaded={onUploaded} />);

    await userEvent.upload(screen.getByTestId("file-input"), [pick("a.pdf"), pick("b.pdf")]);

    await waitFor(() => expect(onUploaded).toHaveBeenCalledTimes(2));
    expect(uploadDocument.mock.calls.map(([options]) => (options as { file: File }).file.name)).toEqual([
      "a.pdf",
      "b.pdf",
    ]);
    expect((uploadDocument.mock.calls[0]?.[0] as { organizationId: string }).organizationId).toBe("org-1");
  });

  it("shows the API's reason and links to the existing document on a duplicate", async () => {
    uploadDocument.mockImplementation(() =>
      Promise.reject(
        new ApiError(409, "duplicate_document", "Este archivo ya está cargado en «Contrato»", [
          { document_id: "d0" },
        ]),
      ),
    );
    render(<DocumentUploader organizationId="org-1" onUploaded={vi.fn()} />);

    await userEvent.upload(screen.getByTestId("file-input"), pick("copia.pdf"));

    expect(await screen.findByText(/ya está cargado en «Contrato»/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver el documento" })).toHaveAttribute("href", "/documents/d0");
  });
});
