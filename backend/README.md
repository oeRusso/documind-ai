# DocuMind AI — backend

API FastAPI (y, desde la etapa 5, workers Celery). Convenciones y reglas: ver `CLAUDE.md` en la raíz.

## Requisitos

- [uv](https://docs.astral.sh/uv/) (instala Python 3.12 solo)
- Podman con `podman compose`

## Primer arranque

```bash
cp .env.example .env              # en la raíz del repo; cambiá las contraseñas
podman compose up -d --build      # PostgreSQL + migraciones + API
```

- API: http://localhost:8000
- Documentación interactiva (Swagger): http://localhost:8000/docs
- Salud: http://localhost:8000/health · Lista para servir: http://localhost:8000/ready

## Desarrollo sin contenedor para la API

```bash
podman compose up -d db
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:create_app --factory --reload
```

## Calidad

```bash
uv run ruff check --fix && uv run ruff format
uv run mypy
uv run pytest            # los tests de integración necesitan `podman compose up -d db`
```

Hooks de git (una sola vez, desde la raíz): `backend/.venv/bin/pre-commit install`.

## Migraciones

```bash
uv run alembic revision -m "describe the change"   # escribí upgrade() y downgrade()
uv run alembic upgrade head
uv run alembic downgrade -1
```

Las migraciones corren con el rol `migrator` (dueño de las tablas). La API usa el rol `app`,
que solo puede leer y escribir filas: no puede cambiar el esquema ni saltarse RLS.
