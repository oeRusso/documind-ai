# DocuMind AI

Plataforma multi-organización de consulta documental con RAG. Cada organización sube sus
documentos (PDF con texto o escaneado, DOCX, TXT, Markdown) y les hace preguntas en español,
y recibe respuestas en streaming con citas verificables: documento, página y fragmento.

Toda la IA corre en local con [Ollama](https://ollama.com), sin APIs comerciales, sobre
software libre y planes gratuitos.

## Estado actual

**Etapas 1, 2 y 4 terminadas** (todo el trabajo nuevo queda en `development` hasta el despliegue):

- Cuentas, organizaciones, roles e invitaciones, con aislamiento entre organizaciones en dos capas
  (chequeo en el backend + Row Level Security en PostgreSQL) y sesiones con refresh token rotativo.
- Documentos: subida de PDF, Word, TXT y Markdown (hasta 25 MB) con validación del tipo real, versiones,
  detección de duplicados, descarga solo por la API y borrado diferido.

Las etapas 0 y 3 (VPS y despliegue) quedan para el final.

```bash
cp .env.example .env                           # completá las contraseñas y JWT_SECRET
podman compose up -d --build                   # base de datos, API, web y Mailpit
podman compose exec api python -m app.dev.seed # usuarios de prueba
```

- Web: http://localhost:3000 (usá `localhost`, no `127.0.0.1`)
- API (Swagger): http://127.0.0.1:8000/docs · Emails de desarrollo: http://127.0.0.1:8025
- Guía con usuarios de prueba: [docs/probar-la-api.md](docs/probar-la-api.md)
- Detalles: [backend/README.md](backend/README.md) y [frontend/README.md](frontend/README.md)

## Stack previsto

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic, Celery + Valkey, PostgreSQL 16 + pgvector.
- **IA:** Ollama (embeddings y LLM locales), búsqueda híbrida (semántica + texto completo).
- **Frontend:** Next.js (App Router), TypeScript, Tailwind CSS, shadcn/ui.
- **Infraestructura:** Podman (local), Docker en el VPS, Caddy, Cloudflare Tunnel, GitHub Actions.

## Documentación

- [Parte 1 — Visión y arquitectura](docs/plan-parte-1-arquitectura.md)
- [Parte 2 — Plan por etapas](docs/plan-parte-2-etapas.md)
- [Etapas](docs/etapas/): objetivo, tareas y criterios de terminado de cada una
- [Decisiones de arquitectura (ADR)](docs/decisions/)
- [Probar la API a mano](docs/probar-la-api.md): usuarios de prueba, Swagger y Mailpit

## Licencia

[AGPL-3.0](LICENSE)
