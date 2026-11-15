# Cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). Las versiones se
publican con un tag sobre `main` al cerrar cada fase; todavía nada llegó a `main` desde la etapa 2
(todo el trabajo queda en `development` hasta el despliegue final).

## [1.0.0] — sin publicar (Fase D: producción y portfolio)

### Agregado
- Métricas de Prometheus desde los eventos de log; dashboard y alertas de Grafana (perfil `monitoring`).
- Analíticas para owners y admins: preguntas por día, sin respuesta (sin autor), valoraciones.
- Backups cifrados con restic, deploy y rollback por etiquetas de imagen, Caddy, runbook.
- Demo pública de solo lectura con reset nocturno y límites por IP.

## [0.3.0] — sin publicar (Fase C: inteligencia)

### Agregado
- Dataset de evaluación (12 leyes, 79 preguntas), embeddings `bge-m3` y búsqueda híbrida con RRF.
- Respuestas con citas validadas en streaming (SSE), umbral de «no encontré evidencia» y cola de
  generación (`llama3.2:3b`).
- Conversaciones privadas, preguntas de seguimiento medidas, alcance por documentos, visor PDF en la
  página citada y botones útil / no útil.
- Defensas contra prompt injection (texto oculto, recordatorio en el prompt, filtro de salida,
  Markdown seguro, CSP) y set de ataques evaluado con el modelo real.
- Bandit, pip-audit y Trivy en CI.

## [0.2.0] — sin publicar (Fase B: pipeline documental)

### Agregado
- Subida segura de documentos (tipo real, tamaño, páginas, duplicados, versiones, borrado diferido).
- Worker con Celery + Valkey: extracción de texto, OCR, limpieza y fragmentos con página y sección.

## [0.1.0] — sin publicar (Fase A: fundamentos)

### Agregado
- Esqueleto del backend (FastAPI, SQLAlchemy async, Alembic, logs JSON, `/health`, `/ready`).
- Cuentas, organizaciones, roles, invitaciones; aislamiento con Row Level Security; sesiones con
  refresh token rotativo y protección CSRF.
- Frontend en Next.js con cliente generado del OpenAPI.
