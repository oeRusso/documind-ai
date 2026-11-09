"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Download, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { DocumentUploader, KindBadge, KindIcon, StatusBadge } from "@/components/documents";
import { ChunkList, ProcessingPanel } from "@/components/processing";
import { ErrorMessage } from "@/components/form";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, errorMessage, inOrganization, unwrap, type VersionRead } from "@/lib/api/client";
import { useAuth } from "@/lib/auth";
import { canDelete, canUpload, downloadDocument, formatBytes, KIND_LABELS } from "@/lib/documents";
import { useActiveOrganization } from "@/lib/organizations";

const date = (value: string) =>
  new Date(value).toLocaleString("es-AR", { dateStyle: "medium", timeStyle: "short" });

export default function DocumentPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const { organization } = useActiveOrganization();
  const queryClient = useQueryClient();
  const organizationId = organization?.id ?? "";
  const key = ["document", organizationId, id];
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const document = useQuery({
    queryKey: key,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/documents/{document_id}", {
          params: { ...inOrganization(organizationId), path: { document_id: id } },
        }),
      ),
    enabled: Boolean(organization),
    retry: false,
  });

  const remove = useMutation({
    mutationFn: async () =>
      unwrap(
        await api.DELETE("/api/v1/documents/{document_id}", {
          params: { ...inOrganization(organizationId), path: { document_id: id } },
        }),
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["documents", organizationId] });
      router.replace("/documents");
    },
  });

  async function download(version: VersionRead) {
    setDownloadError(null);
    try {
      await downloadDocument(organizationId, id, version.filename, version.number);
    } catch (error) {
      setDownloadError(errorMessage(error));
    }
  }

  if (!organization || !user) return null;
  const back = (
    <Link
      href="/documents"
      className="mb-6 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft className="size-4" />
      Documentos
    </Link>
  );

  if (document.isPending) return <>{back}<p className="text-sm text-muted-foreground">Cargando…</p></>;
  if (document.isError) return <>{back}<ErrorMessage message={errorMessage(document.error)} /></>;

  const doc = document.data;
  const latest = doc.versions[0];
  if (!latest) return null;
  const deletable = canDelete(organization.role, doc.created_by_id === user.id);

  return (
    <>
      {back}
      <div className="mb-8 flex flex-wrap items-start gap-4">
        <KindIcon kind={latest.kind} className="size-12" />
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-semibold break-words">{doc.title}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <StatusBadge status={doc.status} />
            <span>·</span>
            <span>
              {doc.versions.length} {doc.versions.length === 1 ? "versión" : "versiones"}
            </span>
          </div>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => void download(latest)}>
            <Download />
            Descargar
          </Button>
          {deletable && (
            <Button
              variant="outline"
              disabled={remove.isPending}
              className="hover:bg-destructive/10 hover:text-destructive"
              onClick={() => {
                if (window.confirm(`¿Borrar «${doc.title}»? Deja de verse para toda la organización.`)) {
                  remove.mutate();
                }
              }}
            >
              <Trash2 />
              Borrar
            </Button>
          )}
        </div>
      </div>

      <div className="grid gap-4">
        <ErrorMessage message={downloadError ?? (remove.error ? errorMessage(remove.error) : null)} />
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <Card className="gap-0 overflow-hidden pb-0">
          <CardHeader className="pb-6">
            <CardTitle>Versiones</CardTitle>
          </CardHeader>
          <div className="border-t">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Versión</TableHead>
                  <TableHead>Archivo</TableHead>
                  <TableHead>Subida por</TableHead>
                  <TableHead className="text-right">
                    <span className="sr-only">Descargar</span>
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {doc.versions.map((version) => (
                  <TableRow key={version.number}>
                    <TableCell>
                      <span className="rounded-md bg-muted px-2 py-0.5 text-xs font-medium">v{version.number}</span>
                    </TableCell>
                    <TableCell>
                      <span className="block max-w-64 truncate font-medium">{version.filename}</span>
                      <span className="text-xs text-muted-foreground">
                        {formatBytes(version.size_bytes)}
                        {version.page_count != null && ` · ${version.page_count} páginas`}
                      </span>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      <span className="block">{version.uploaded_by_email ?? "—"}</span>
                      <span className="text-xs">{date(version.created_at)}</span>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label={`Descargar versión ${version.number}`}
                        onClick={() => void download(version)}
                      >
                        <Download />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </Card>

        <div className="grid content-start gap-6">
          <ProcessingPanel
            organizationId={organizationId}
            documentId={id}
            canReprocess={deletable}
            onFinished={() =>
              Promise.all([
                queryClient.invalidateQueries({ queryKey: key }),
                queryClient.invalidateQueries({ queryKey: ["chunks", organizationId, id] }),
              ])
            }
          />
          <Card>
            <CardHeader>
              <CardTitle>Detalles</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid gap-3 text-sm">
                <Detail label="Tipo">
                  <KindBadge kind={latest.kind} />
                </Detail>
                <Detail label="Páginas">{latest.page_count ?? "—"}</Detail>
                <Detail label="Tamaño">{formatBytes(latest.size_bytes)}</Detail>
                <Detail label="Subido por">{doc.created_by_email ?? "—"}</Detail>
                <Detail label="Creado">{date(doc.created_at)}</Detail>
                <Detail label="Huella SHA-256">
                  <code className="text-xs break-all text-muted-foreground" title={latest.sha256}>
                    {latest.sha256.slice(0, 16)}…
                  </code>
                </Detail>
              </dl>
            </CardContent>
          </Card>

          {canUpload(organization.role) && (
            <Card>
              <CardHeader>
                <CardTitle>Subir versión nueva</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-3">
                <p className="text-sm text-muted-foreground">
                  Por ejemplo, el {KIND_LABELS[latest.kind] ?? "archivo"} corregido. Las versiones anteriores se
                  conservan.
                </p>
                <DocumentUploader
                  compact
                  multiple={false}
                  organizationId={organizationId}
                  path={`/api/v1/documents/${id}/versions`}
                  onUploaded={() => queryClient.invalidateQueries({ queryKey: key })}
                />
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      <div className="mt-6">
        <ChunkList organizationId={organizationId} documentId={id} />
      </div>
    </>
  );
}

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right font-medium">{children}</dd>
    </div>
  );
}
