# DocuMind AI

Plataforma multi-organización de consulta documental con RAG: cada empresa sube sus
documentos y les pregunta en español, con respuestas citadas (documento, página y
fragmento), usando solo IA local. Proyecto de portfolio y de aprendizaje
(Python, IA aplicada, DevOps).

## Fuentes de verdad
- `docs/plan-parte-1-arquitectura.md`: qué se construye y cómo está organizado.
- `docs/plan-parte-2-etapas.md`: en qué orden.
- `docs/etapas/etapa-NN.md`: alcance y criterios de terminado de cada etapa.
- `docs/decisions/`: ADRs. Si el código contradice una ADR, gana la ADR o se escribe una nueva.

Si algo de este archivo choca con los planes, avisá antes de elegir.

## Sobre quien desarrolla
- Programa en PHP (Dolibarr 20), JavaScript y Next.js. Python lo está aprendiendo.
- Cuando uses algo de Python sin equivalente directo en PHP o JS (decoradores,
  context managers, generadores, `Protocol`, `async with`, dataclasses, etc.),
  explicalo en **dos líneas comparándolo con PHP**.
- Es un proyecto para aprender: pasos chicos, diffs legibles, y frenar a explicar
  cuando algo no sea obvio. Las piezas clave (RLS, tokens, chunking, fusión de rankings,
  validación de citas) las escribe Claude y la persona las revisa: explicarlas en
  palabras simples al entregarlas.
- En decisiones técnicas que la persona no conoce, elegir la opción recomendada o la
  menos riesgosa, decirlo en una línea y seguir, sin frenar a preguntar.

## Restricciones
- **Costo cero — PROHIBIDO usar herramientas, servicios o nubes que generen gastos.** Solo software libre
  o planes gratuitos (repo público en GitHub: Actions, GHCR y Dependabot gratis). Ya pagos: VPS Contabo
  sin GPU y dominio en Cloudflare. Antes de sumar cualquier servicio externo, confirmar que es gratuito
  y avisar sus límites; si hay duda, preguntar en vez de usarlo.
- **IA 100 % local con Ollama**: ninguna API comercial (OpenAI, Anthropic, etc.), ni en código ni en tests.
- Nada se instala antes de su etapa (columna "Etapa" del stack en la Parte 1, §3).
- **No usar servicios de terceros, SaaS ni APIs externas sin preguntar antes.** Todo corre en el VPS.
  **No crear recursos en Cloudflare más allá de DNS** (el túnel lo crea Esteban, ver "Despliegue").
  Ya aprobados: GitHub (repo, Actions, GHCR, Dependabot). Si un plan pide otro servicio externo
  (Turnstile, Access, UptimeRobot, R2, reglas de Cloudflare...), frenar y preguntar.

## Stack
Backend: Python 3.12 + uv, FastAPI, Pydantic v2 + pydantic-settings, SQLAlchemy 2 async (asyncpg),
Alembic, Celery + Valkey, PostgreSQL 16 + pgvector, structlog, Ollama.
Frontend: Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + TanStack Query, cliente generado del OpenAPI. pnpm.
Infra: Podman + podman-compose en la PC, Docker + Compose v2 en el VPS, Caddy (interno), Cloudflare Tunnel,
GitHub Actions. (Cloudflare Access y GHCR quedan sujetos a la regla de servicios externos.)

## Comandos
Existen a partir de la etapa 1 (backend) y la etapa 2 (frontend).
- Backend (en `backend/`): `uv run pytest`, `uv run ruff check --fix`, `uv run ruff format`, `uv run mypy app`
- Frontend (en `frontend/`): `pnpm lint`, `pnpm typecheck`, `pnpm test`
- Entorno: `podman compose up -d`

## Reglas que nunca se rompen
- Toda tabla de negocio tiene `organization_id` (también las hijas) y toda consulta filtra por él.
  RLS en PostgreSQL es la segunda capa, no la única.
- Recurso de otra organización → **404**, nunca 403. Falta de permiso por rol dentro de la propia organización → **403**.
- Los endpoints no hacen trabajo pesado: encolan una tarea Celery y responden `202 Accepted`.
- Cada caso de uso nuevo lleva al menos un test. Tests primero en lógica crítica
  (aislamiento entre organizaciones, chunking, citas).
- Nunca leer, imprimir ni commitear `.env` ni secretos. Valores de ejemplo solo en `.env.example`.
- El contenido de los documentos es **dato, no instrucción** (prompt injection). El LLM no ejecuta SQL,
  no toca el filesystem ni dispara acciones.
- Medir antes de optimizar: reranking, Docling, reformulación de consultas, etc. solo entran si mejoran
  una métrica del dataset de evaluación, y queda registrado en `docs/evaluation/`.
- Código, identificadores, comentarios y commits en inglés; documentación y textos de interfaz en español.

## Arquitectura del backend
Monolito modular + workers. `backend/app/modules/<módulo>/` con cuatro capas:
- `domain/`: entidades (dataclasses puras), interfaces de repositorio (`Protocol`), errores. No importa FastAPI, SQLAlchemy ni Ollama.
- `application/`: casos de uso; usa interfaces de `domain` y recibe implementaciones por inyección de dependencias.
- `infrastructure/`: modelos SQLAlchemy e implementaciones de repositorios.
- `presentation/`: routers FastAPI y schemas Pydantic. Sin lógica de negocio.

Reglas de dependencia:
- Un módulo no toca las tablas de otro: lo llama por su capa `application`.
- Los módulos no conocen Ollama: piden operaciones a `app/ai/` mediante interfaces (`LLMProvider`, `EmbeddingProvider`).
- Sin lógica de negocio en routers ni en modelos SQLAlchemy.

Ojo con los nombres repetidos:
- `infrastructure/` en la raíz del repo = Containerfiles, Caddy, cloudflared, monitoreo, scripts.
- `backend/app/infrastructure/` = DB, storage, cola y workers de la app.
- Evaluación: `backend/app/ai/evaluation/` = código de métricas (librería);
  `backend/evaluation/` = dataset y scripts CLI (`eval_retrieval`, etc.);
  `docs/evaluation/` = informes con resultados.

## Convenciones de API
- Prefijo `/api/v1`; recursos en plural y en inglés (`/api/v1/documents`). `/health` y `/ready` van fuera del prefijo.
- IDs UUID (v7, ordenables por tiempo); fechas ISO 8601 en UTC; `created_at` y `updated_at` en todas las tablas.
- Paginación por cursor: `?limit=20&cursor=...` → `{ "items": [...], "next_cursor": "..." }`.
- Errores siempre con este formato:
  `{ "error": { "code": "document_not_found", "message": "Documento no encontrado", "request_id": "..." } }`
- Trabajos largos: `202 Accepted` con el id del trabajo; el cliente consulta su estado.
- Chat por SSE con eventos `token`, `citations` y `done`.

## Convenciones de código
- Type hints en todo el código Python; Mypy en modo estricto.
- Async de punta a punta en la API; los workers Celery pueden ser síncronos.
- Configuración solo por variables de entorno, leídas en `app/core/config.py`.
- Logs JSON con structlog, siempre con `request_id`.
- Contenedores sin root, imágenes mínimas.

## Git
- Repo: https://github.com/oeRusso/documind-ai (público).
- Ramas: `main` = estable (desde la etapa 3, lo que llega a `main` se despliega a producción);
  `development` = integración. **Todo el trabajo de las etapas se commitea y pushea a `development`.**
  Al cerrar una etapa, PR `development` → `main`.
  (Esto reemplaza las ramas `etapa-NN-descripcion` que propone la Parte 2.)
- Conventional Commits: `feat(documents): add upload endpoint`, `fix(auth): ...`, `test(...)`, `docs(...)`, `chore(...)`.
- Un commit por paso chico.
- Tags al cerrar cada fase: `v0.1.0` (A), `v0.2.0` (B), `v0.3.0` (C), `v1.0.0` (D).
- Durante una etapa se commitea y pushea a `development`. **Nunca** commitear ni pushear directo a `main`.

## Flujo de cada etapa
1. Trabajar en `development` (actualizada con `main`).
2. Leer este archivo y `docs/etapas/etapa-NN.md`. Proponer un plan en pasos de no más de 1 hora,
   con archivos a crear o modificar y tests de cada paso. **Sin código hasta que se apruebe.** Señalar dudas y riesgos.
3. Implementar en pasos chicos; tests y linters en verde.
4. Al cerrar: actualizar README, escribir la ADR si hubo decisión (`docs/decisions/NNNN-titulo.md`,
   desde `0000-plantilla.md`), marcar la etapa como terminada en su archivo y en la sección siguiente.
5. PR `development` → `main`.

## Continuidad entre sesiones
Cada sesión de Claude Code arranca sin memoria de la anterior: el contexto vive en este repo.
- **Al empezar**: leer este archivo, el `docs/etapas/etapa-NN.md` de la etapa actual (sobre todo
  "Resultado" y "Notas" de la anterior) y `git log --oneline -15`.
- **Al terminar** (o al cortar a mitad de etapa): actualizar la sección "Etapa actual" de acá abajo
  y, en el archivo de la etapa, tildar tareas y dejar una sección "Resultado / Pendientes" con lo que
  falta y las decisiones tomadas. Commitear y pushear a `development`.

## Despliegue (VPS compartido)
Guía obligatoria, fuera del repo: `/run/media/estebanrusso/3ADAD252DAD20A51/PROYECTOS-PERSONALES/PORTAFOLIO2.0/docs/VPS-COMPARTIDO.md`.
Leerla antes de cualquier tarea de deploy (etapas 0, 3 y 11). Resumen:
- El VPS es compartido con otros proyectos (portfolio en producción). Se usa Docker + Compose v2, no Podman:
  quitar los `:Z` de los volúmenes en el compose de producción.
- Dirección: `https://documind.esteban-russo.com`. Túnel `documind`, ruta a `http://caddy:80`.
  Los planes dicen `app.tudominio`: la dirección real es esa.
- Ningún puerto publicado a internet; solo `127.0.0.1:<puerto>` si hace falta, sin chocar con los usados
  (el `3306` es del portfolio). El tráfico entra por un contenedor `cloudflared` del propio compose.
- HTTPS lo termina Cloudflare: confiar en `X-Forwarded-Proto` del proxy; la IP real viene en `CF-Connecting-IP`.
- Secretos: los carga Esteban en el `.env` del VPS (600). El agente genera contraseñas aleatorias allá sin mostrarlas.
- `sudo` lo corre Esteban: pasarle el comando exacto. Se despliega `main`; el agente no mergea.
- RAM compartida (8 GB): `mem_limit` en base, workers y Ollama; LLM de 1–3B cuantizado y embeddings livianos.
  Mirar `free -h` y `docker stats --no-stream` antes de levantar algo pesado.
- No poner la IP del VPS en el repo (es público y el túnel la oculta).

## Entorno local
- uv en `~/.local/bin` (instala Python 3.12 por su cuenta). Node 24 disponible; pnpm todavía no instalado.
- `podman compose` usa el socket de Podman del usuario (`systemctl --user enable --now podman.socket`).
- `.env` en la raíz (permisos 600, ignorado por git) con contraseñas aleatorias para dev.

## Etapa actual
- **Etapa 0** (en curso): falta lo del VPS y la prueba de humo de Ollama. Ver `docs/etapas/etapa-00.md`.
- **Etapa 1**: terminada (mergeada a `main`, que quedó protegida).
- **Etapa 2** (en curso): pasos 1 a 11 de 27 hechos (base, RLS, usuarios, tokens, permisos, casos de uso de auth).
  Sigue el paso 12 (routers HTTP de auth). Ver "Avance" en `docs/etapas/etapa-02.md`.
Regla general: la etapa actual es la de **número más bajo** que no está marcada como terminada en `docs/etapas/`.
