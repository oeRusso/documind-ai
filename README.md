# DocuMind AI

Plataforma multi-organización de consulta documental con RAG. Cada organización sube sus
documentos (PDF con texto o escaneado, DOCX, TXT, Markdown) y les hace preguntas en español,
y recibe respuestas en streaming con citas verificables: documento, página y fragmento.

Toda la IA corre en local con [Ollama](https://ollama.com), sin APIs comerciales, sobre
software libre y planes gratuitos.

## Estado actual

**Etapas 1, 2, 4, 5, 6 y 7 terminadas** (todo el trabajo nuevo queda en `development` hasta el despliegue):

- Cuentas, organizaciones, roles e invitaciones, con aislamiento entre organizaciones en dos capas
  (chequeo en el backend + Row Level Security en PostgreSQL) y sesiones con refresh token rotativo.
- Documentos: subida de PDF, Word, TXT y Markdown (hasta 25 MB) con validación del tipo real, versiones,
  detección de duplicados, descarga solo por la API y borrado diferido.
- Procesamiento en segundo plano: texto página por página, OCR de páginas escaneadas (Tesseract) y
  fragmentos por título con su página y sección, visibles en la web.
- Búsqueda híbrida (por significado con embeddings locales `bge-m3`, y por palabras en español), medida
  sobre un dataset de 12 leyes argentinas: recall@5 = 0,912 ([informe](docs/evaluation/retrieval-2026-11-11.md)).
- Preguntas con respuesta citada (página **Preguntar**): la respuesta aparece mientras se escribe y cada dato
  lleva su cita `[n]` al documento y la página. Si los documentos no lo responden, dice «no encontré evidencia»
  sin inventar. Las citas inventadas se descartan, y las preguntas esperan su turno en una cola
  ([informe](docs/evaluation/answers-2026-11-12.md), [ADR 0009](docs/decisions/0009-modelo-de-lenguaje-y-respuestas.md)).

Las etapas 0 y 3 (VPS y despliegue) quedan para el final.

```bash
cp .env.example .env                           # completá las contraseñas y JWT_SECRET
podman compose up -d --build                   # base de datos, API, web y Mailpit
podman compose exec api python -m app.dev.seed # usuarios de prueba
podman compose exec ollama ollama pull bge-m3       # embeddings (búsqueda)
podman compose exec ollama ollama pull llama3.2:3b  # modelo de lenguaje (respuestas)
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

## Licencias de los modelos

Las respuestas las genera **Llama 3.2** (`llama3.2:3b`), con la
[Llama 3.2 Community License](https://www.llama.com/llama3_2/license/). **Built with Llama.**
Los embeddings usan `bge-m3` (MIT). Los modelos se descargan del registro gratuito de Ollama y corren
en local: ningún texto sale del servidor.
