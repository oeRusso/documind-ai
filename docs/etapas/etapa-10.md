# Etapa 10 — Observabilidad y analíticas

- **Fase:** D — Producción y portfolio
- **Duración estimada:** 1 semana
- **Rama:** `development` (PR a `main` al cerrar la etapa)
- **Estado:** terminada (2026-11-15), en `development`

## Objetivo

Ver qué pasa dentro del sistema y mostrarlo en un dashboard.

## Tareas

- [x] Métricas de la API con `prometheus-fastapi-instrumentator`, más métricas propias del pipeline y del RAG.
- [x] Prometheus con retención corta (7 a 15 días) para cuidar disco y RAM; exportadores de nodo, PostgreSQL y Celery. Configuración en `infrastructure/monitoring/`.
- [x] Grafana detrás de Cloudflare Access, nunca expuesto directo. **Sin Cloudflare Access (decisión 2026-11-15): solo en `127.0.0.1`, túnel SSH en el VPS.**
- [x] Dashboard con: tiempo de procesamiento por página, errores de extracción y OCR, tiempo de embeddings, latencia de búsqueda, tiempo hasta el primer token, tokens por segundo, CPU y RAM, tasa de citas válidas.
- [x] Alertas gratuitas de Grafana por email o Telegram: API caída, cola de trabajos creciendo, RAM sobre 90 %.
- [x] Módulo `analytics` para admins de cada organización: documentos procesados, preguntas por día y **preguntas sin respuesta**.
- [ ] (Opcional, no entra) trazas con OpenTelemetry y errores con GlitchTip.

## Fuera de alcance

- Backups con restic + R2, Quadlet, runbook (etapa 11).
- Retención larga de métricas.

## Criterios de terminado

- [x] Una pregunta lenta se puede diagnosticar en el dashboard: búsqueda, cola o generación.
- [ ] Una alerta de prueba llega a tu teléfono. **Llega por email a Mailpit; al teléfono falta que Esteban elija el canal (Telegram o SMTP).**

## Notas

- Con 8 GB de RAM, vigilar el consumo de Prometheus y Grafana: si hace falta, apagar Grafana fuera de las demos (riesgo "el VPS no alcanza para el LLM").
- **Regla de servicios externos** (`CLAUDE.md`): Grafana detrás de Cloudflare Access requiere permiso de Esteban.
  Alternativa sin Cloudflare: Grafana solo en `127.0.0.1` y acceso por túnel SSH.

- **Lo que deja la etapa 9** (ADR 0011): los eventos `hidden_text_dropped`, `unsafe_output_removed` e
  `invalid_citations_dropped` en los logs son señales de seguridad para el dashboard.

## Resultado

**Criterios:** una pregunta lenta se diagnostica en el panel «¿Dónde se va el tiempo de una
respuesta?» (búsqueda, cola, primer token, generación). La alerta de prueba llega a Mailpit; al
teléfono falta elegir canal (ADR 0012).

**Qué quedó:**

- `app/core/metrics.py`: métricas desde los eventos de log (procesador de structlog), `/metrics` en
  la API (`prometheus-fastapi-instrumentator`) y puerto 9101 en el worker.
- `--profile monitoring` en `compose.yaml`: Prometheus, Grafana (http://127.0.0.1:3001, usuario
  `admin`, contraseña en `GRAFANA_ADMIN_PASSWORD` del `.env`), exportadores de nodo, PostgreSQL y Valkey.
- `infrastructure/monitoring/`: configuración de Prometheus y reglas, dashboard «DocuMind» y tres
  alertas (API caída, cola creciendo, RAM > 90 %) aprovisionadas.
- Módulo `analytics` (`GET /api/v1/analytics/overview?days=7|30|90`, owners y admins) y página
  **Analíticas** con preguntas por día, sin respuesta (sin autor), valoraciones y documentos.

**Pendientes:**

- Canal de alertas al teléfono: Telegram, más adelante (decisión de Esteban, 2026-11-15).
- En el VPS (etapa 3): rol `monitor` con `pg_monitor` para el exportador, en vez del usuario `postgres`.
- OpenTelemetry y GlitchTip: no entran (más servicios y RAM para un VPS de 8 GB).

## Referencias

- Parte 1: §8 (métricas que se miden).
