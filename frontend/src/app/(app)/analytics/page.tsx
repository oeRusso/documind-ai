"use client";

import { useQuery } from "@tanstack/react-query";
import { HelpCircle } from "lucide-react";
import { useState } from "react";

import { ErrorMessage } from "@/components/form";
import { PageHeader } from "@/components/people";
import { Card } from "@/components/ui/card";
import { QuestionsChart } from "@/features/analytics/questions-chart";
import { api, errorMessage, inOrganization, unwrap } from "@/lib/api/client";
import { useActiveOrganization } from "@/lib/organizations";
import { canViewAnalytics } from "@/lib/roles";
import { cn } from "@/lib/utils";

const PERIODS = [7, 30, 90] as const;

function percent(part: number, total: number): string {
  return total ? `${Math.round((part / total) * 100)} %` : "—";
}

export default function AnalyticsPage() {
  const { organization } = useActiveOrganization();
  const [days, setDays] = useState<(typeof PERIODS)[number]>(30);
  const organizationId = organization?.id ?? "";
  const allowed = organization ? canViewAnalytics(organization.role) : false;

  const overview = useQuery({
    queryKey: ["analytics", organizationId, days],
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/analytics/overview", {
          params: { ...inOrganization(organizationId), query: { days } },
        }),
      ),
    enabled: allowed,
  });

  if (!organization) return null;
  if (!allowed) {
    return (
      <>
        <PageHeader title="Analíticas" />
        <ErrorMessage message="Solo los owners y administradores ven las analíticas de la organización." />
      </>
    );
  }
  const data = overview.data;
  const answeredTotal = data ? data.answered + data.no_evidence : 0;

  return (
    <>
      <PageHeader
        title="Analíticas"
        description={
          <>
            Uso de <strong className="font-medium text-foreground">{organization.name}</strong>. Las preguntas de
            cada persona son privadas: acá solo hay totales y las preguntas que los documentos no pudieron responder.
          </>
        }
        actions={
          <div role="group" aria-label="Período" className="flex rounded-lg border p-0.5 text-sm">
            {PERIODS.map((n) => (
              <button
                key={n}
                type="button"
                aria-pressed={days === n}
                onClick={() => setDays(n)}
                className={cn("rounded-md px-3 py-1", days === n ? "bg-muted font-medium" : "text-muted-foreground")}
              >
                {n} días
              </button>
            ))}
          </div>
        }
      />
      <ErrorMessage message={overview.error ? errorMessage(overview.error) : null} />
      {overview.isPending && <p className="text-sm text-muted-foreground">Cargando…</p>}
      {data && (
        <div className="grid gap-6">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Preguntas" value={data.questions} detail={`${data.people} personas`} />
            <Stat
              label="Sin respuesta"
              value={percent(data.no_evidence, answeredTotal)}
              detail={`${data.no_evidence} de ${answeredTotal}`}
            />
            <Stat
              label="Útiles"
              value={percent(data.helpful, data.helpful + data.not_helpful)}
              detail={`${data.helpful} útiles · ${data.not_helpful} no útiles`}
            />
            <Stat
              label="Documentos procesados"
              value={data.documents_ready}
              detail={`${data.pages} páginas${data.ocr_pages ? ` · ${data.ocr_pages} con OCR` : ""}${data.documents_failed ? ` · ${data.documents_failed} con error` : ""}`}
            />
          </div>

          <Card className="gap-3 p-5">
            <h2 className="text-sm font-semibold">Preguntas por día</h2>
            {data.questions === 0 ? (
              <p className="text-sm text-muted-foreground">Todavía no hay preguntas en este período.</p>
            ) : (
              <QuestionsChart points={data.questions_by_day} />
            )}
          </Card>

          <Card className="gap-3 p-5">
            <div>
              <h2 className="text-sm font-semibold">Preguntas sin respuesta</h2>
              <p className="text-sm text-muted-foreground">
                Los documentos no tenían la información. Sirven para saber qué documentos faltan subir.
              </p>
            </div>
            {data.unanswered.length === 0 ? (
              <p className="text-sm text-muted-foreground">Ninguna en este período.</p>
            ) : (
              <ul className="grid gap-2">
                {data.unanswered.map((item, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    <HelpCircle className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                    <span className="flex-1">{item.question}</span>
                    <time className="shrink-0 text-xs text-muted-foreground" dateTime={item.asked_at}>
                      {new Date(item.asked_at).toLocaleDateString("es-AR")}
                    </time>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          {data.documents_pending > 0 && (
            <p className="text-sm text-muted-foreground">{data.documents_pending} documentos se están procesando.</p>
          )}
        </div>
      )}
    </>
  );
}

function Stat({ label, value, detail }: { label: string; value: string | number; detail: string }) {
  return (
    <Card className="gap-1 p-4">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className="text-2xl font-semibold tabular-nums">{value}</p>
      <p className="text-xs text-muted-foreground">{detail}</p>
    </Card>
  );
}
