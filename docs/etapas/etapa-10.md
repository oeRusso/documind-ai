# Etapa 10 — Observabilidad y analíticas

- **Fase:** D — Producción y portfolio
- **Duración estimada:** 1 semana
- **Rama:** `development` (PR a `main` al cerrar la etapa)
- **Estado:** pendiente

## Objetivo

Ver qué pasa dentro del sistema y mostrarlo en un dashboard.

## Tareas

- [ ] Métricas de la API con `prometheus-fastapi-instrumentator`, más métricas propias del pipeline y del RAG.
- [ ] Prometheus con retención corta (7 a 15 días) para cuidar disco y RAM; exportadores de nodo, PostgreSQL y Celery. Configuración en `infrastructure/monitoring/`.
- [ ] Grafana detrás de Cloudflare Access, nunca expuesto directo.
- [ ] Dashboard con: tiempo de procesamiento por página, errores de extracción y OCR, tiempo de embeddings, latencia de búsqueda, tiempo hasta el primer token, tokens por segundo, CPU y RAM, tasa de citas válidas.
- [ ] Alertas gratuitas de Grafana por email o Telegram: API caída, cola de trabajos creciendo, RAM sobre 90 %.
- [ ] Módulo `analytics` para admins de cada organización: documentos procesados, preguntas por día y **preguntas sin respuesta**.
- [ ] Opcional: trazas con OpenTelemetry y errores con GlitchTip.

## Fuera de alcance

- Backups con restic + R2, Quadlet, runbook (etapa 11).
- Retención larga de métricas.

## Criterios de terminado

- [ ] Una pregunta lenta se puede diagnosticar en el dashboard: búsqueda, cola o generación.
- [ ] Una alerta de prueba llega a tu teléfono.

## Notas

- Con 8 GB de RAM, vigilar el consumo de Prometheus y Grafana: si hace falta, apagar Grafana fuera de las demos (riesgo "el VPS no alcanza para el LLM").
- **Regla de servicios externos** (`CLAUDE.md`): Grafana detrás de Cloudflare Access requiere permiso de Esteban.
  Alternativa sin Cloudflare: Grafana solo en `127.0.0.1` y acceso por túnel SSH.

## Referencias

- Parte 1: §8 (métricas que se miden).
