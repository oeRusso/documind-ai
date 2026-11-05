# Etapa 1 — Esqueleto del backend

- **Fase:** A — Fundamentos
- **Duración estimada:** 1 semana
- **Rama:** `development` (PR a `main` al cerrar la etapa)
- **Estado:** pendiente

## Objetivo

Una API FastAPI profesional, sin lógica de negocio todavía, que sirva de molde para todo lo demás.

## Tareas

- [ ] Proyecto con uv (`backend/pyproject.toml`); app factory en `app/main.py`; configuración con `pydantic-settings` en `app/core/config.py`.
- [ ] Logs JSON con structlog y un `request_id` por petición.
- [ ] Manejo de errores centralizado (`app/core/exceptions.py`) con el formato de error uniforme de la Parte 1, §9.
- [ ] PostgreSQL 16 con pgvector en `compose.yaml`; SQLAlchemy 2 async.
- [ ] Primera migración con Alembic: extensión `vector` y tabla `organizations`.
- [ ] Dos roles de base de datos desde el principio: el de la app (`DATABASE_URL`) y el de migraciones (`DATABASE_MIGRATION_URL`).
- [ ] Endpoints `/health` (vivo) y `/ready` (DB accesible).
- [ ] Calidad: ruff, mypy estricto, pytest con base de datos de prueba, pre-commit (con detect-secrets).
- [ ] Containerfile multi-stage que corre como usuario sin root (en `infrastructure/containers/`).
- [ ] GitHub Actions: lint, tipos y tests en cada push, con PostgreSQL + pgvector como servicio. Dependabot y CodeQL activados.
- [ ] Módulo de ejemplo con las cuatro capas (domain, application, infrastructure, presentation) que sirva de plantilla.

## Fuera de alcance

- Usuarios, autenticación, memberships, RLS (etapa 2).
- Frontend (etapa 2).
- Caddy, Cloudflare Tunnel, deploy y `compose.prod.yaml` (etapa 3).
- Valkey, Celery y workers (etapa 5).
- Prometheus, Grafana, OpenTelemetry (etapa 10); acá solo logs JSON y `/health`/`/ready`.
- Bandit, pip-audit y Trivy en CI (etapa 9).

## Criterios de terminado

- [ ] `podman compose up` levanta API y base de datos, y `/ready` devuelve 200.
- [ ] El CI está en verde y bloquea merges si falla.
- [ ] Existe un módulo de ejemplo con las cuatro capas (domain, application, infrastructure, presentation) que sirve de plantilla.

## Notas

- **`.gitkeep` en `backend/migrations/`**: `alembic init migrations` falla si la carpeta no está vacía. Borrar el `.gitkeep` antes de generarla.
- **UUID v7**: ni Python 3.12 ni PostgreSQL 16 lo generan de forma nativa (llega en Python 3.14 con `uuid.uuid7()` y en PostgreSQL 18 con `uuidv7()`). Opciones: una librería (p. ej. `uuid-utils`) o subir versiones. Decidirlo en una ADR.
- Variables de entorno que entran en esta etapa: `APP_ENV`, `DATABASE_URL`, `DATABASE_MIGRATION_URL`. Probablemente también haga falta `POSTGRES_*` para el contenedor de la base.

## Referencias

- Parte 1: §3 (stack, etapa 1), §4 (estructura y capas), §5 (convenciones de tablas), §8 (CI), §9 (convenciones).
