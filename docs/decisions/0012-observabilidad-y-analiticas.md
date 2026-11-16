# 0012 — Observabilidad y analíticas

- **Estado:** aceptada
- **Fecha:** 2026-11-15
- **Etapa:** 10

## Contexto

Hay que poder diagnosticar una pregunta lenta (¿búsqueda, cola o generación?), recibir alertas y
darle a los admins números de uso, sin servicios pagos ni de terceros, en un VPS de 8 GB compartido.
Las conversaciones son privadas de cada persona (ADR 0010).

## Opciones consideradas

**Cómo medir**
1. Llamar a Prometheus desde cada caso de uso: mete una librería de infraestructura en `application`.
2. **Convertir en métricas los eventos que ya se loguean** (`page_extracted`, `answer_generated`...)
   con un procesador de structlog: el dominio no cambia, y log y métrica salen del mismo evento.
3. OpenTelemetry (trazas): más completo, pero más servicios y RAM. Opcional en el plan; no entra.

**Acceso a Grafana**
1. Cloudflare Access: servicio externo (`CLAUDE.md`), descartado por decisión de Esteban (2026-11-15).
2. **Solo en `127.0.0.1`**, y en el VPS por túnel SSH (`ssh -L 3001:127.0.0.1:3001 vps`).

**Alertas**
1. **Email desde Grafana** (Mailpit en desarrollo).
2. Telegram (bot propio): gratis, pero es un servicio de terceros y necesita un token de Esteban.

**Analíticas y privacidad**
1. Mostrar las conversaciones de todos a los admins: rompe la ADR 0010.
2. **Solo totales**, más las preguntas que los documentos no pudieron responder, **sin autor**: es lo
   que le dice a un admin qué documentos faltan.

## Decisión

Opción 2 en cada punto. El monitoreo va en un perfil del compose (`--profile monitoring`) para no
gastar RAM cuando no se usa: Prometheus (10 días o 1 GB), Grafana, node, postgres y valkey exporters,
256 MB como mucho cada servicio grande. Las analíticas son para owners y admins (`VIEW_ANALYTICS`),
y el módulo `analytics` pide los números a `conversations` e `ingestion` por su capa `application`.

## Consecuencias

- Agregar una métrica es agregar una línea en `app/core/metrics.py` para un evento que ya existe.
  Si se renombra un evento de log, la métrica deja de moverse: los tests de `test_metrics.py` lo cubren.
- `/metrics` está fuera de `/api/v1`: Caddy no lo enruta (etapa 3), solo lo lee Prometheus.
- Ollama no da los tokens en el stream: la velocidad se mide en caracteres por segundo.
- Las alertas a un teléfono necesitan que Esteban elija el canal (Telegram o un SMTP); hasta entonces
  llegan por email (Mailpit en local).
- Las preguntas del endpoint sin estado `POST /chat` no se guardan, así que no cuentan en las
  analíticas (la web usa conversaciones).

## Evidencia

- Prueba con el entorno levantado: dos preguntas reales → `documind_search_seconds` (1,6 s de
  promedio), `documind_answer_first_token_seconds` (18 s) y `documind_answer_generation_seconds` (27 s)
  separados en el panel «¿Dónde se va el tiempo de una respuesta?».
- Alerta de prueba de Grafana recibida en Mailpit.
- Tests: `tests/unit/test_metrics.py` y `tests/integration/test_analytics_api.py` (403 para viewer,
  números por organización, preguntas sin autor).
