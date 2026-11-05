# DocuMind AI

Plataforma multi-organización de consulta documental con RAG. Cada organización sube sus
documentos (PDF con texto o escaneado, DOCX, TXT, Markdown) y les hace preguntas en español,
y recibe respuestas en streaming con citas verificables: documento, página y fragmento.

Toda la IA corre en local con [Ollama](https://ollama.com), sin APIs comerciales, sobre
software libre y planes gratuitos.

## Estado actual

**Etapa 0 en curso**: preparación del VPS y del repositorio. Todavía no hay código de la aplicación.

## Stack previsto

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic, Celery + Valkey, PostgreSQL 16 + pgvector.
- **IA:** Ollama (embeddings y LLM locales), búsqueda híbrida (semántica + texto completo).
- **Frontend:** Next.js (App Router), TypeScript, Tailwind CSS, shadcn/ui.
- **Infraestructura:** Podman, Caddy, Cloudflare Tunnel, GitHub Actions.

## Documentación

- [Parte 1 — Visión y arquitectura](docs/plan-parte-1-arquitectura.md)
- [Parte 2 — Plan por etapas](docs/plan-parte-2-etapas.md)
- [Etapas](docs/etapas/): objetivo, tareas y criterios de terminado de cada una
- [Decisiones de arquitectura (ADR)](docs/decisions/)

## Licencia

[AGPL-3.0](LICENSE)
