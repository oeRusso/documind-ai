"use client";

import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import Link from "next/link";

import { DocumentUploader, KindBadge, KindIcon, StatusBadge } from "@/components/documents";
import { ErrorMessage } from "@/components/form";
import { PageHeader } from "@/components/people";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, errorMessage, inOrganization, unwrap } from "@/lib/api/client";
import { canUpload, formatBytes } from "@/lib/documents";
import { useActiveOrganization } from "@/lib/organizations";

const PAGE_SIZE = 20;

export default function DocumentsPage() {
  const { organization } = useActiveOrganization();
  const queryClient = useQueryClient();
  const organizationId = organization?.id ?? "";
  const key = ["documents", organizationId];

  const documents = useInfiniteQuery({
    queryKey: key,
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.GET("/api/v1/documents", {
          params: { ...inOrganization(organizationId), query: { limit: PAGE_SIZE, cursor: pageParam } },
        }),
      ),
    getNextPageParam: (last) => last.next_cursor ?? null,
    enabled: Boolean(organization),
  });

  if (!organization) return null;
  const items = documents.data?.pages.flatMap((page) => page.items) ?? [];
  const uploader = canUpload(organization.role);

  return (
    <>
      <PageHeader
        title="Documentos"
        description={
          <>
            Archivos de <strong className="font-medium text-foreground">{organization.name}</strong>: solo los
            ve tu organización.
          </>
        }
      />

      {uploader && (
        <div className="mb-8">
          <DocumentUploader
            organizationId={organizationId}
            onUploaded={() => queryClient.invalidateQueries({ queryKey: key })}
          />
        </div>
      )}

      <div className="mb-4">
        <ErrorMessage message={documents.error ? errorMessage(documents.error) : null} />
      </div>

      <Card className="overflow-hidden py-0">
        {documents.isPending && <p className="p-6 text-sm text-muted-foreground">Cargando…</p>}
        {documents.isSuccess && items.length === 0 && (
          <div className="grid place-items-center gap-2 px-6 py-14 text-center">
            <span className="grid size-12 place-items-center rounded-full bg-muted text-muted-foreground">
              <FileText className="size-5" />
            </span>
            <p className="font-medium">Todavía no hay documentos</p>
            <p className="max-w-sm text-sm text-muted-foreground">
              {uploader
                ? "Subí contratos, manuales o políticas: en las próximas etapas vas a poder hacerles preguntas."
                : "Cuando alguien de tu organización suba documentos, van a aparecer acá."}
            </p>
          </div>
        )}
        {items.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Documento</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead>Tamaño</TableHead>
                <TableHead>Subido por</TableHead>
                <TableHead>Estado</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((doc) => (
                <TableRow key={doc.id}>
                  <TableCell>
                    <Link href={`/documents/${doc.id}`} className="group flex items-center gap-3">
                      <KindIcon kind={doc.latest_version.kind} />
                      <span className="grid min-w-0">
                        <span className="truncate font-medium group-hover:text-primary group-hover:underline">
                          {doc.title}
                        </span>
                        <span className="truncate text-xs text-muted-foreground">
                          {doc.latest_version.filename}
                          {doc.latest_version.number > 1 && ` · versión ${doc.latest_version.number}`}
                        </span>
                      </span>
                    </Link>
                  </TableCell>
                  <TableCell>
                    <span className="flex items-center gap-2">
                      <KindBadge kind={doc.latest_version.kind} />
                      {doc.latest_version.page_count != null && (
                        <span className="text-xs text-muted-foreground">
                          {doc.latest_version.page_count} pág.
                        </span>
                      )}
                    </span>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatBytes(doc.latest_version.size_bytes)}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    <span className="block">{doc.created_by_email ?? "—"}</span>
                    <span className="text-xs">
                      {new Date(doc.created_at).toLocaleDateString("es-AR", { dateStyle: "medium" })}
                    </span>
                  </TableCell>
                  <TableCell>
                    <StatusBadge status={doc.status} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      {documents.hasNextPage && (
        <div className="mt-4 flex justify-center">
          <Button variant="outline" onClick={() => void documents.fetchNextPage()} disabled={documents.isFetchingNextPage}>
            {documents.isFetchingNextPage ? "Cargando…" : "Ver más"}
          </Button>
        </div>
      )}
    </>
  );
}
