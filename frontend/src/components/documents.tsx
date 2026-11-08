"use client";

import { AlertCircle, CheckCircle2, FileText, FileType2, Loader2, UploadCloud } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";

import { errorMessage } from "@/lib/api/client";
import {
  ACCEPT_ATTRIBUTE,
  duplicateOf,
  formatBytes,
  KIND_LABELS,
  MAX_UPLOAD_MB,
  STATUS_LABELS,
  uploadDocument,
} from "@/lib/documents";
import { cn } from "@/lib/utils";

const KIND_STYLES: Record<string, string> = {
  pdf: "bg-rose-500/10 text-rose-700 dark:text-rose-300",
  docx: "bg-sky-500/10 text-sky-700 dark:text-sky-300",
  txt: "bg-muted text-muted-foreground",
  md: "bg-violet-500/10 text-violet-700 dark:text-violet-300",
};

export function KindIcon({ kind, className }: { kind: string; className?: string }) {
  const Icon = kind === "pdf" || kind === "docx" ? FileText : FileType2;
  return (
    <span
      aria-hidden="true"
      className={cn("grid size-9 shrink-0 place-items-center rounded-lg", KIND_STYLES[kind], className)}
    >
      <Icon className="size-4" />
    </span>
  );
}

export function KindBadge({ kind }: { kind: string }) {
  return (
    <span className={cn("rounded-md px-2 py-0.5 text-xs font-medium", KIND_STYLES[kind])}>
      {KIND_LABELS[kind] ?? kind}
    </span>
  );
}

const STATUS_STYLES: Record<string, string> = {
  pending: "bg-warning/10 text-warning ring-warning/25",
  processing: "bg-sky-500/10 text-sky-700 ring-sky-500/25 dark:text-sky-300",
  ready: "bg-success/10 text-success ring-success/25",
  failed: "bg-destructive/10 text-destructive ring-destructive/25",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={cn(
        "inline-flex w-fit items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset",
        STATUS_STYLES[status],
      )}
    >
      <span className="size-1.5 rounded-full bg-current" />
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

type UploadItem = {
  key: string;
  name: string;
  size: number;
  progress: number;
  state: "waiting" | "uploading" | "done" | "error";
  error?: string;
  duplicateId?: string | null;
};

/**
 * Drop zone + upload queue. Files go one at a time (the server validates each one fully),
 * each with its own progress bar and result.
 */
export function DocumentUploader({
  organizationId,
  onUploaded,
  path,
  multiple = true,
  compact = false,
}: {
  organizationId: string;
  onUploaded: () => void | Promise<void>;
  /** Upload a new version instead of a new document. */
  path?: string;
  multiple?: boolean;
  compact?: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [items, setItems] = useState<UploadItem[]>([]);
  const busy = items.some((item) => item.state === "uploading" || item.state === "waiting");

  function update(key: string, patch: Partial<UploadItem>) {
    setItems((current) => current.map((item) => (item.key === key ? { ...item, ...patch } : item)));
  }

  async function start(files: File[]) {
    if (files.length === 0) return;
    const queued = files.map((file, index) => ({
      file,
      item: {
        key: `${Date.now()}-${index}-${file.name}`,
        name: file.name,
        size: file.size,
        progress: 0,
        state: "waiting" as const,
      },
    }));
    setItems((current) => [...queued.map((q) => q.item), ...current].slice(0, 20));
    for (const { file, item } of queued) {
      update(item.key, { state: "uploading" });
      try {
        await uploadDocument({
          organizationId,
          file,
          path,
          onProgress: (fraction) => update(item.key, { progress: fraction }),
        });
        update(item.key, { state: "done", progress: 1 });
        await onUploaded();
      } catch (error) {
        update(item.key, { state: "error", error: errorMessage(error), duplicateId: duplicateOf(error) });
      }
    }
  }

  return (
    <div className="grid gap-3">
      <div
        role="button"
        tabIndex={0}
        aria-label="Elegir archivos para subir"
        onClick={() => input.current?.click()}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            input.current?.click();
          }
        }}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          const files = Array.from(event.dataTransfer.files);
          void start(multiple ? files : files.slice(0, 1));
        }}
        className={cn(
          "grid cursor-pointer place-items-center gap-2 rounded-2xl border-2 border-dashed bg-card text-center transition-colors outline-none hover:border-primary/50 hover:bg-accent/40 focus-visible:ring-2 focus-visible:ring-ring/50",
          compact ? "px-4 py-5" : "px-6 py-10",
          dragging && "border-primary bg-accent/60",
        )}
      >
        <span className="grid size-11 place-items-center rounded-full bg-primary/10 text-primary">
          {busy ? <Loader2 className="size-5 animate-spin" /> : <UploadCloud className="size-5" />}
        </span>
        <p className="text-sm font-medium">
          {multiple ? "Arrastrá archivos acá o " : "Arrastrá el archivo acá o "}
          <span className="text-primary">elegilos desde tu computadora</span>
        </p>
        <p className="text-xs text-muted-foreground">
          PDF, Word (.docx), TXT o Markdown · hasta {MAX_UPLOAD_MB} MB
        </p>
        <input
          ref={input}
          type="file"
          accept={ACCEPT_ATTRIBUTE}
          multiple={multiple}
          className="hidden"
          data-testid="file-input"
          onChange={(event) => {
            const files = Array.from(event.target.files ?? []);
            event.target.value = ""; // choosing the same file again fires onChange again
            void start(files);
          }}
        />
      </div>

      {items.length > 0 && (
        <ul className="grid gap-2" aria-label="Archivos subidos">
          {items.map((item) => (
            <li key={item.key} className="rounded-xl border bg-card px-4 py-3 text-sm">
              <div className="flex items-center gap-3">
                {item.state === "done" ? (
                  <CheckCircle2 className="size-4 shrink-0 text-success" />
                ) : item.state === "error" ? (
                  <AlertCircle className="size-4 shrink-0 text-destructive" />
                ) : (
                  <Loader2 className="size-4 shrink-0 animate-spin text-muted-foreground" />
                )}
                <span className="min-w-0 flex-1 truncate font-medium">{item.name}</span>
                <span className="shrink-0 text-xs text-muted-foreground">{formatBytes(item.size)}</span>
              </div>
              {(item.state === "uploading" || item.state === "waiting") && (
                <div
                  role="progressbar"
                  aria-label={`Subiendo ${item.name}`}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(item.progress * 100)}
                  className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted"
                >
                  <div
                    className="h-full rounded-full bg-primary transition-[width] duration-200"
                    style={{ width: `${Math.max(item.progress * 100, 3)}%` }}
                  />
                </div>
              )}
              {item.state === "error" && (
                <p className="mt-1.5 pl-7 text-xs text-destructive">
                  {item.error}
                  {item.duplicateId && (
                    <>
                      {" "}
                      <Link href={`/documents/${item.duplicateId}`} className="font-medium underline">
                        Ver el documento
                      </Link>
                    </>
                  )}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
