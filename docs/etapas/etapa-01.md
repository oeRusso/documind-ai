# Etapa 1 — Esqueleto del backend

- **Fase:** A — Fundamentos
- **Duración estimada:** 1 semana
- **Rama:** `development` (PR a `main` al cerrar la etapa)
- **Estado:** en revisión (falta proteger `main` y el PR `development` → `main`)

## Objetivo

Una API FastAPI profesional, sin lógica de negocio todavía, que sirva de molde para todo lo demás.

## Tareas

- [x] Proyecto con uv (`backend/pyproject.toml`); app factory en `app/main.py`; configuración con `pydantic-settings` en `app/core/config.py`.
- [x] Logs JSON con structlog y un `request_id` por petición.
- [x] Manejo de errores centralizado (`app/core/exceptions.py`) con el formato de error uniforme de la Parte 1, §9.
- [x] PostgreSQL 16 con pgvector en `compose.yaml`; SQLAlchemy 2 async.
- [x] Primera migración con Alembic: extensión `vector` y tabla `organizations`.
- [x] Dos roles de base de datos desde el principio: el de la app (`DATABASE_URL`) y el de migraciones (`DATABASE_MIGRATION_URL`).
- [x] Endpoints `/health` (vivo) y `/ready` (DB accesible).
- [x] Calidad: ruff, mypy estricto, pytest con base de datos de prueba, pre-commit (con detect-secrets).
- [x] Containerfile multi-stage que corre como usuario sin root (en `infrastructure/containers/`).
- [x] GitHub Actions: lint, tipos y tests en cada push, con PostgreSQL + pgvector como servicio. Dependabot y CodeQL activados.
- [x] Módulo de ejemplo con las cuatro capas (domain, application, infrastructure, presentation) que sirva de plantilla.

## Fuera de alcance

- Usuarios, autenticación, memberships, RLS (etapa 2).
- Frontend (etapa 2).
- Caddy, Cloudflare Tunnel, deploy y `compose.prod.yaml` (etapa 3).
- Valkey, Celery y workers (etapa 5).
- Prometheus, Grafana, OpenTelemetry (etapa 10); acá solo logs JSON y `/health`/`/ready`.
- Bandit, pip-audit y Trivy en CI (etapa 9).

## Criterios de terminado

- [x] `podman compose up` levanta API y base de datos, y `/ready` devuelve 200.
- [ ] El CI está en verde y bloquea merges si falla. *(En verde: sí. Bloqueo: falta activar la protección de la rama `main` en GitHub, con el check "lint, types and tests" como obligatorio.)*
- [x] Existe un módulo de ejemplo con las cuatro capas (domain, application, infrastructure, presentation) que sirve de plantilla.

## Notas

- **`.gitkeep` en `backend/migrations/`**: `alembic init migrations` falla si la carpeta no está vacía. Borrar el `.gitkeep` antes de generarla.
- **UUID v7**: resuelto con `uuid-utils` (ADR 0002).
- Variables de entorno que entraron: `APP_ENV`, `LOG_LEVEL`, `LOG_FORMAT`, `DATABASE_URL`, `DATABASE_MIGRATION_URL`, y para compose `POSTGRES_PASSWORD`, `APP_DB_PASSWORD`, `MIGRATOR_DB_PASSWORD`.

## Resultado

- Módulo plantilla: `backend/app/modules/organizations/` (domain, application, infrastructure, presentation). Endpoints `POST /api/v1/organizations` y `GET /api/v1/organizations/{id}`, **sin autenticación hasta la etapa 2**.
- Dos roles de base: `migrator` (dueño de las tablas, corre Alembic) y `app` (solo DML, sin `BYPASSRLS`). Script: `infrastructure/scripts/db-init/10-roles.sh`.
- La sesión de base se abre por request con `Depends(get_session, scope="function")`: el commit ocurre **antes** de enviar la respuesta.
- UUID v7 con `uuid-utils`: ver ADR 0002.
- 32 tests (unitarios, integración y seguridad de roles); CI en GitHub Actions en verde.

## Referencias

- Parte 1: §3 (stack, etapa 1), §4 (estructura y capas), §5 (convenciones de tablas), §8 (CI), §9 (convenciones).
