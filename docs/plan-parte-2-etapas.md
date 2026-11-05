# Parte 2 — Plan por etapas

Nov 2, 2026 · @Esteban Russo

## Resumen

La arquitectura de la Parte 1 no se construye de una vez: se levanta en **13 etapas cortas (0 a 12), agrupadas en 4 fases**, donde cada etapa termina con algo que funciona, se prueba y se puede mostrar.

Mejoras respecto al primer borrador de la arquitectura:

- **Etapa 0 de dimensionamiento**: el VPS de Contabo no tiene GPU, así que el modelo de IA se elige según la RAM real, no al revés.
- **Stack mínimo primero, stack completo después**: Docling, reranking, OpenTelemetry, Prometheus y Grafana pasan a etapas tardías y solo entran si aportan algo medible.
- **Cloudflare Tunnel en lugar de abrir puertos**: el VPS no expone nada a Internet, ni siquiera el 443.
- **Embeddings livianos sin PyTorch** al inicio (vía Ollama o FastEmbed/ONNX), para no inflar las imágenes ni la RAM.
- **Deploy temprano**: el sistema llega a producción en la etapa 3, vacío pero con CI/CD, en vez de esperar a la semana 10.
- **Evaluación del RAG con un dataset propio** antes de optimizar nada.
- **Un flujo de trabajo concreto para Claude Code**: un `CLAUDE.md`, decisiones registradas (ADR) y un prompt base por etapa.

Costo adicional: **cero**. Todo es software libre o tiene un plan gratuito suficiente para un proyecto de portfolio.

## Principios y decisiones clave

Se mantiene el **monolito modular con workers asíncronos**, pero con un stack mínimo que crece etapa por etapa.

### Cinco reglas para todo el proyecto

1. **Una etapa = una rama = un entregable demostrable.** Si no se puede mostrar en 2 minutos, la etapa no terminó.
2. **Rebanadas verticales antes que capas horizontales.** Mejor un upload que funciona de punta a punta (UI → API → DB → disco) que un backend perfecto sin interfaz.
3. **Nada pesado dentro de una petición HTTP.** Extracción, OCR, embeddings y generación larga van a workers.
4. **`organization_id` en todas las tablas desde el día 1.** Agregar multi-tenancy después cuesta el triple.
5. **Medir antes de optimizar.** Reranking, búsqueda híbrida o Docling solo entran si mejoran una métrica de tu dataset de evaluación.

### Dimensionar el VPS antes de elegir modelos

El VPS no tiene GPU: todo corre en CPU compartida. Revisá qué plan tenés (`free -h`, `nproc`, `df -h`) y elegí el modelo según esta tabla. Valores de referencia de los planes Cloud VPS de Contabo; confirmalos en tu panel.

| Plan Contabo | vCPU / RAM | Qué entra cómodo | LLM sugerido para empezar |
| --- | --- | --- | --- |
| Cloud VPS 10 | 4 / 8 GB | Todo el stack, justo | Modelo de 1,5B a 4B cuantizado (Q4) |
| Cloud VPS 20 | 6 / 12 GB | Todo el stack con margen | Modelo de 3B a 4B (Q4) |
| Cloud VPS 30 | 8 / 24 GB | Stack + monitoreo completo | Modelo de 7B a 8B (Q4) |

Presupuesto aproximado de RAM con 8 GB: PostgreSQL 1 GB, Valkey 0,1 GB, API 0,4 GB, worker con OCR 1 GB, Next.js 0,4 GB, Ollama con un modelo 4B unos 3 a 3,5 GB, y el resto para el sistema. En CPU compartida esperá pocas decenas de tokens por segundo como máximo: **la respuesta siempre se muestra en streaming**. Tu RX 6600 queda para experimentar en local con modelos más grandes.

Candidatos a evaluar en las etapas 6 y 7 (no fijarlos antes): familia Qwen pequeña (3 a 4B), Gemma pequeña, Phi-4 Mini y Granite. Criterio: calidad en español sobre tu dataset, licencia, RAM y tokens por segundo en el VPS.

### Stack ajustado

| Área | Plan original | Ajuste | Motivo |
| --- | --- | --- | --- |
| Gestor Python | — | **uv** + `pyproject.toml` | Rápido, reproducible, estándar actual |
| Backend | FastAPI + Pydantic | Igual, con SQLAlchemy 2 async + asyncpg | Sin cambios de fondo |
| Colas | Celery + Redis | Celery + **Valkey** | Valkey es el fork BSD de Redis, compatible y 100 % libre |
| Embeddings | Sentence Transformers + BGE-M3 | **Ollama** (bge-m3) o **FastEmbed** (ONNX) | Evita PyTorch: imágenes de cientos de MB en vez de varios GB |
| Parsing | Docling + PyMuPDF | **PyMuPDF + OCRmyPDF/Tesseract** primero; Docling en etapa 9 | Docling es pesado en CPU; entra si mejora tablas medibles |
| Búsqueda | pgvector | pgvector + **full-text de PostgreSQL** (español) | Búsqueda híbrida sin otra base de datos |
| Proxy | Caddy expuesto | **Cloudflare Tunnel** → Caddy interno | Ningún puerto abierto, TLS gestionado por Cloudflare |
| Contenedores | Podman Compose | Podman Compose en dev y prod; Quadlet opcional | Arranque con systemd sin depender de un daemon |
| Frontend | Next.js + Tailwind | + shadcn/ui, TanStack Query, cliente TS generado del OpenAPI | Tipos sincronizados con el backend sin escribirlos a mano |
| Observabilidad | OTel + Prometheus + Grafana | Logs JSON + `/health` al inicio; Prometheus/Grafana en etapa 10 | Ahorra RAM y complejidad en las primeras semanas |

Ojo con una licencia: **PyMuPDF es AGPL**. Para un repo público de portfolio no es problema; si algún día se vuelve producto cerrado, se reemplaza por pypdf o pdfplumber.

## Servicios gratuitos de terceros

Tu cuenta de Cloudflare ya cubre casi todo lo externo; el resto son planes gratuitos de GitHub y herramientas self-hosted. Los límites de los planes gratis cambian: revisalos al activar cada uno.

| Servicio | Para qué | Etapa | Nota |
| --- | --- | --- | --- |
| Cloudflare DNS + proxy | Dominio, CDN, protección DDoS | 3 | Ya lo tenés |
| Cloudflare Tunnel (`cloudflared`) | Publicar la app sin abrir puertos en el VPS | 3 | Reemplaza exponer Caddy al 443 |
| Cloudflare Access (Zero Trust) | Proteger Grafana, panel admin y demo privada con login | 3 y 10 | Plan gratuito para equipos chicos |
| Cloudflare Turnstile | CAPTCHA en registro y login | 2 | Alternativa libre de rastreo a reCAPTCHA |
| Cloudflare R2 | Destino de backups cifrados (restic) | 11 | Plan gratuito de algunos GB, sin costo de egreso |
| GitHub (repo público) | Código, issues, project board | 0 | Público = Actions y GHCR gratis |
| GitHub Actions | CI: lint, tipos, tests, build, deploy | 1 y 3 | Ilimitado en repos públicos |
| GitHub Container Registry | Guardar imágenes de contenedores | 3 | Gratis para imágenes públicas |
| Dependabot + CodeQL | Actualizaciones y análisis de seguridad | 1 | Gratis en repos públicos |
| Hugging Face Hub | Descargar modelos de embeddings y reranking | 5 | Sin cuenta para modelos públicos |
| Mailpit (self-hosted) | Ver emails de desarrollo (invitaciones, reset) | 2 | Solo dev; en prod un plan gratis de email transaccional si lo necesitás |
| UptimeRobot o Uptime Kuma | Avisarte si la app se cae | 3 | Externo es mejor: si el VPS cae, Kuma cae con él |
| GlitchTip (self-hosted) o Sentry plan Developer | Captura de errores backend y frontend | 10 | Opcional |

Lo que **no** hace falta: Auth0, Clerk, Pinecone, OpenAI, Vercel ni ningún cloud pago. Todo eso lo resolvés dentro del VPS.

## Cómo trabajar con Claude Code

Claude Code rinde mejor con contexto estable y tareas acotadas: un `CLAUDE.md` en la raíz, un archivo por etapa y una sesión por tarea.

### Archivos de contexto que conviene crear en la etapa 0

Antes de la primera sesión, exportá cada pestaña de este documento a Markdown y guardalas en el repo como `docs/plan-parte-1-arquitectura.md` y `docs/plan-parte-2-etapas.md`. Son la fuente de verdad que Claude Code lee.

- `CLAUDE.md`: stack, comandos, convenciones y reglas que nunca se rompen.
- `docs/etapas/etapa-XX.md`: objetivo, alcance, fuera de alcance y criterios de terminado de cada etapa (copialos de este documento).
- `docs/decisions/NNNN-titulo.md`: una ADR corta por decisión importante (por qué Valkey, por qué pgvector, qué modelo). Son oro para una entrevista.

Esqueleto sugerido de `CLAUDE.md`:

```markdown
# DocuMind AI

## Stack
Backend: Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic, Celery + Valkey, PostgreSQL 16 + pgvector, Ollama.
Frontend: Next.js (App Router) + TypeScript + Tailwind + shadcn/ui.
Infra: Podman Compose, Caddy, Cloudflare Tunnel.

## Comandos
- Backend: `uv run pytest`, `uv run ruff check --fix`, `uv run ruff format`, `uv run mypy app`
- Frontend: `pnpm lint`, `pnpm typecheck`, `pnpm test`
- Entorno: `podman compose up -d`

## Reglas
- Toda tabla de negocio tiene organization_id y toda consulta filtra por él.
- Los endpoints no hacen trabajo pesado: encolan una tarea Celery.
- Cada caso de uso nuevo lleva al menos un test.
- Nunca leer, imprimir ni commitear .env ni secretos.
- Código e identificadores en inglés; documentación en español.
- Módulos: domain / application / infrastructure / presentation. domain no importa FastAPI ni SQLAlchemy.

## Etapa actual
Ver docs/etapas/ (la de número más alto sin marcar como terminada).
```

### Ciclo de cada etapa

1. Rama nueva: `etapa-04-pipeline`.
2. Pedile a Claude Code un **plan antes de código** (modo plan) a partir de `docs/etapas/etapa-04.md`. Revisalo y recortalo.
3. Implementación en pasos chicos, un commit por paso. Revisá cada diff: el objetivo también es aprender Python.
4. Tests y linters en verde, en local y en CI.
5. Pedile que actualice el README, la ADR si hubo una decisión, y que marque la etapa como terminada.
6. Pull request, merge, y sesión nueva para la etapa siguiente.

### Prompt base por etapa

```text
Leé CLAUDE.md y docs/etapas/etapa-04.md.
Proponé un plan de implementación en pasos de no más de 1 hora,
indicando archivos a crear o modificar y tests para cada paso.
No escribas código todavía. Señalá dudas o riesgos.
Cuando uses un concepto de Python que no tenga equivalente directo
en PHP o JavaScript, explicalo en dos líneas comparándolo con PHP.
```

### Consejos prácticos

- **Una tarea por sesión**: contexto limpio, menos errores. Al cambiar de tarea, sesión nueva.
- **Pre-commit** con ruff, mypy y detect-secrets: atrapa errores aunque el código lo escriba la IA.
- **No pegues secretos reales** en el chat; usá `.env.example` con valores falsos.
- **Pedile tests primero** en lógica crítica (aislamiento entre organizaciones, chunking, citas).
- **Cuando algo no lo entiendas, frená** y pedí una explicación antes de seguir: es un proyecto para aprender, no solo para entregar.

## Fase A — Fundamentos (etapas 0 a 3, unas 3,5 semanas)

Al final de la Fase A tenés una app vacía pero real: login multi-organización, en producción en tu dominio, con CI/CD. Todavía sin IA, a propósito.

### Etapa 0 — Preparación y prueba de humo del VPS (2 a 3 días)

Objetivo: eliminar el mayor riesgo del proyecto (que el VPS no aguante un LLM) antes de escribir una línea de la app.

- Endurecer el VPS: usuario sin root con sudo, SSH solo con llave, login por contraseña deshabilitado, firewall que solo permita SSH, actualizaciones automáticas de seguridad.
- Crear swap de 4 GB si tenés 8 GB de RAM: evita que el sistema mate procesos en picos.
- Instalar Podman, `podman-compose` y `cloudflared`.
- Prueba de humo de IA: levantar Ollama en un contenedor, bajar 2 o 3 modelos candidatos y medir RAM, tokens por segundo y calidad con 5 preguntas en español.
- Preparar el entorno local: Python 3.12 con uv, Node LTS con pnpm, Podman Desktop.
- Crear el repo con la estructura de carpetas, `CLAUDE.md`, `.gitignore`, `.env.example` y licencia (si usás PyMuPDF, AGPL-3.0 es la opción coherente).

Terminado cuando:

- [ ] El VPS solo acepta SSH con llave y no tiene otros puertos abiertos.
- [ ] `docs/decisions/0001-vps-y-modelo.md` registra la RAM disponible, los modelos probados y sus tokens por segundo.
- [ ] El repo existe en GitHub con `CLAUDE.md` y los archivos de etapas.

### Etapa 1 — Esqueleto del backend (1 semana)

Objetivo: una API FastAPI profesional, sin lógica de negocio todavía, que sirva de molde para todo lo demás.

- Proyecto con uv; app factory en `main.py`; configuración con `pydantic-settings`; logs JSON con structlog y un `request_id` por petición.
- Manejo de errores centralizado (`core/exceptions.py`) con respuestas de error uniformes.
- PostgreSQL 16 con pgvector en `compose.yaml`; SQLAlchemy 2 async; primera migración con Alembic (extensión `vector` y tabla `organizations`).
- Endpoints `/health` (vivo) y `/ready` (DB accesible).
- Calidad: ruff, mypy estricto, pytest con base de datos de prueba, pre-commit.
- Containerfile multi-stage que corre como usuario sin root.
- GitHub Actions: lint, tipos y tests en cada push, con PostgreSQL como servicio.

Terminado cuando:

- [ ] `podman compose up` levanta API y base de datos, y `/ready` devuelve 200.
- [ ] El CI está en verde y bloquea merges si falla.
- [ ] Existe un módulo de ejemplo con las cuatro capas (domain, application, infrastructure, presentation) que sirve de plantilla.

### Etapa 2 — Autenticación, organizaciones y multi-tenancy (1,5 semanas)

Objetivo: que ninguna organización pueda ver datos de otra, garantizado por dos capas independientes.

- Tablas `users`, `organizations`, `memberships` y roles owner, admin, member y viewer.
- Contraseñas con Argon2id; access token de 15 minutos; refresh token rotativo, revocable y guardado en cookie HttpOnly, Secure, SameSite.
- Dependencia de FastAPI que resuelve el usuario y su membresía, y entrega el `organization_id` a cada caso de uso.
- Row Level Security en PostgreSQL: la app fija `app.current_org` por transacción y usa un rol de base de datos que no puede saltarse RLS.
- Invitaciones por link, rate limit en login, tabla `audit_logs` con las acciones de seguridad.
- Frontend mínimo en Next.js: registro, login, selector de organización y gestión de miembros, con un cliente TypeScript generado desde el OpenAPI.

Terminado cuando:

- [ ] Un test demuestra que un usuario de la organización A no lee datos de B, incluso con el filtro del backend deshabilitado (lo frena RLS).
- [ ] Reusar un refresh token ya rotado invalida la sesión.
- [ ] Un viewer recibe 403 al intentar acciones de admin.

### Etapa 3 — Primer deploy y CI/CD (3 a 4 días)

Objetivo: que cada merge a `main` llegue solo a producción, desde ahora y para siempre.

- Imagen de Next.js con salida `standalone`; `compose.prod.yaml` con Caddy, API, web y PostgreSQL en una red interna.
- Cloudflare Tunnel: `cloudflared` conecta el VPS con Cloudflare y enruta `app.tudominio` a Caddy; Caddy reparte `/api` al backend y el resto al frontend.
- GitHub Actions: build de imágenes, push a GitHub Container Registry, deploy por SSH (`pull`, `alembic upgrade head`, `up -d`).
- Secretos solo en GitHub Secrets y en un `.env` del VPS con permisos 600.
- Backup diario con `pg_dump` en el VPS (el destino externo llega en la etapa 11) y monitoreo externo con UptimeRobot.

Terminado cuando:

- [ ] Un merge a `main` está en producción en menos de 10 minutos sin tocar el VPS.
- [ ] `https://app.tudominio` muestra el login, y un escaneo externo no encuentra puertos abiertos salvo SSH.
- [ ] Restauraste un backup en una base vacía al menos una vez.

## Fase B — Pipeline documental (etapas 4 y 5, unas 2,5 semanas)

Al final de la Fase B subís un PDF, escaneado o no, y en segundos ves su estado avanzar hasta "listo", con el texto dividido en fragmentos que saben de qué página vienen.

### Etapa 4 — Upload y almacenamiento seguro (1 semana)

Objetivo: guardar documentos de forma privada, validada y aislada por organización.

- Tablas `documents` y `document_versions`, con hash SHA-256 para detectar duplicados.
- Upload por streaming (sin cargar el archivo entero en memoria) con límite de tamaño. Cloudflare en plan gratuito corta las peticiones de más de 100 MB: fijá un máximo menor, por ejemplo 25 MB.
- Validación del tipo real por firma de archivo (no por extensión), cantidad de páginas y rechazo de PDFs cifrados o corruptos.
- Interfaz `StorageBackend` con implementación en filesystem: rutas `/{org_id}/{uuid}`, nombres aleatorios, sin path traversal. La interfaz permite cambiar a almacenamiento S3 compatible sin tocar el módulo `documents`.
- Descarga solo a través de la API con permisos; nunca una URL pública al archivo.
- Borrado lógico, y borrado físico diferido para respetar los backups.
- Frontend: lista de documentos, upload con barra de progreso, detalle con metadatos.

Terminado cuando:

- [ ] Un `.exe` renombrado a `.pdf` es rechazado.
- [ ] Un usuario de otra organización recibe 404 al pedir el documento (404, no 403, para no revelar que existe).
- [ ] Subir el mismo archivo dos veces crea una versión nueva o avisa del duplicado, no dos documentos sueltos.

### Etapa 5 — Workers, extracción, OCR y chunking (1,5 semanas)

Objetivo: un pipeline asíncrono confiable que convierte cualquier documento soportado en fragmentos con referencia a página y sección.

- Valkey y Celery en el compose; tabla `processing_jobs` con estados: pendiente, extrayendo, OCR, fragmentando, listo, fallido.
- Tareas idempotentes (reprocesar no duplica nada), reintentos con espera creciente, timeout por tarea y mensaje de error guardado cuando falla.
- El worker recibe `organization_id` y `document_id`, y vuelve a verificar la pertenencia antes de procesar.
- Contenedor del worker con límites de memoria y CPU, y como máximo 1 o 2 tareas a la vez para no ahogar al LLM.
- Extracción con PyMuPDF página por página. Las páginas con poco texto pasan por OCRmyPDF con Tesseract en español e inglés.
- Soporte inicial: PDF, DOCX, TXT y Markdown. Nada más hasta que esto sea sólido.
- Normalización: Unicode, guiones de corte de línea, encabezados y pies de página repetidos.
- Chunking por estructura (títulos y párrafos) con tamaño máximo de unos 400 a 600 tokens y solapamiento pequeño; cada fragmento guarda página inicial, página final y sección.
- Frontend: estado del procesamiento en vivo (polling o Server-Sent Events) y vista de los fragmentos de un documento.

Terminado cuando:

- [ ] Un PDF escaneado termina con texto legible en sus fragmentos.
- [ ] Matar el worker a mitad de un proceso y reiniciarlo no deja el documento trabado ni duplicado.
- [ ] Hay tests de chunking con documentos de ejemplo guardados en `tests/fixtures`.
- [ ] Registrás el tiempo de procesamiento por página en los logs.

## Fase C — Inteligencia: búsqueda, RAG y evaluación (etapas 6 a 9, unas 5,5 semanas)

Al final de la Fase C preguntás en español sobre tus documentos y recibís una respuesta en streaming con citas que abren la página exacta del PDF, y tenés números que prueban que funciona.

### Etapa 6 — Dataset de evaluación, embeddings y búsqueda híbrida (1,5 semanas)

Objetivo: recuperar los fragmentos correctos, y poder medirlo, antes de que intervenga ningún LLM.

- **Primero el dataset**: 10 a 20 documentos públicos en español (normativa, manuales, contratos modelo) y 50 a 100 preguntas con documento y página esperados. Incluí un 15 % de preguntas sin respuesta en los documentos.
- Interfaz `EmbeddingProvider` con implementación en Ollama o FastEmbed; compará dos modelos multilingües.
- Tabla de embeddings con nombre y versión del modelo, para poder reindexar al cambiarlo; índice HNSW de pgvector.
- Búsqueda de texto completo de PostgreSQL con configuración en español y `unaccent`, índice GIN.
- Fusión de ambos rankings con Reciprocal Rank Fusion; el filtro por organización y por documentos se aplica dentro de la consulta, nunca después.
- Endpoint `/search` y página de búsqueda en el frontend.
- Script `eval_retrieval` que calcula recall@5 y MRR sobre el dataset.

Terminado cuando:

- [ ] Tenés recall@5 y MRR medidos para búsqueda vectorial, textual e híbrida, y la comparación está en una ADR.
- [ ] Una búsqueda responde en menos de 300 ms con todos tus documentos de prueba cargados.

### Etapa 7 — RAG con citas y streaming (1,5 semanas)

Objetivo: respuestas fundamentadas, con citas verificables, que digan "no lo sé" cuando corresponde.

- Interfaz `LLMProvider` con implementación en Ollama; elegí el modelo con los datos de la etapa 0 y del dataset.
- Prompt con reglas fijas: responder solo con el contexto, citar con marcadores `[n]` y declarar falta de evidencia. Los fragmentos van delimitados y marcados como datos, no como instrucciones.
- Constructor de contexto con presupuesto de tokens (los modelos chicos rinden mejor con contextos cortos) y unión de fragmentos contiguos.
- Si la mejor coincidencia queda bajo un umbral, se responde "no encontré evidencia" **sin llamar al LLM**: ahorra CPU y evita inventos.
- Validación de citas: cada `[n]` debe apuntar a un fragmento entregado; las inválidas se descartan y se registran.
- Streaming con Server-Sent Events de FastAPI a Next.js.
- Semáforo de generación: 1 o 2 respuestas simultáneas como máximo; las demás esperan en cola y el usuario ve su posición.
- Ollama con el modelo precargado y `keep_alive` largo, para no pagar la carga en cada pregunta.

Terminado cuando:

- [ ] Una pregunta sin respuesta en los documentos devuelve "no encontré evidencia" y no una invención.
- [ ] Cinco preguntas simultáneas no tiran abajo el VPS: se encolan y se responden.
- [ ] Cada cita guarda documento, página y fragmento.

### Etapa 8 — Conversaciones y experiencia de chat (1 semana)

Objetivo: la demo central del portfolio, de punta a punta.

- Tablas `conversations`, `messages` y `citations`; historial por usuario y organización.
- Preguntas de seguimiento: la consulta de búsqueda combina la pregunta actual con el último turno. Reformular con el LLM cuesta otra llamada en CPU: hacelo solo si el dataset muestra mejora.
- Alcance de la conversación: todos los documentos de la organización o una selección.
- Interfaz: chat con streaming, panel de citas con el fragmento resaltado y visor PDF (pdf.js) abierto en la página citada.
- Botones "útil / no útil" por respuesta; las marcadas como no útiles alimentan el dataset.

Terminado cuando:

- [ ] El recorrido subir documento → preguntar → hacer clic en la cita → ver la página funciona en producción.
- [ ] Un viewer puede consultar pero no subir ni borrar documentos.

### Etapa 9 — Evaluación continua y seguridad de IA (1,5 semanas)

Objetivo: convertir "parece que anda" en números, y blindar el sistema contra documentos maliciosos.

- Suite de evaluación: recall@k y MRR (recuperación), tasa de citas válidas, tasa de abstención correcta en preguntas sin respuesta. La evaluación de recuperación corre en CI; la completa, con LLM, corre en tu PC con la RX 6600.
- Set de prompt injection: documentos con instrucciones ocultas ("ignorá tus reglas", texto blanco sobre blanco, links a sitios externos). El modelo no debe obedecerlas.
- Salida segura en el frontend: Markdown sin HTML crudo y sin cargar imágenes ni links externos automáticamente (evita filtrar datos).
- Experimentos que solo se quedan si mejoran las métricas: reranking con un cross-encoder multilingüe (medí la latencia en CPU), Docling para documentos con tablas, ajuste del tamaño de los fragmentos.
- Seguridad del código en CI: Bandit, pip-audit y Trivy sobre las imágenes.

Terminado cuando:

- [ ] `docs/evaluation/` tiene un informe con métricas antes y después de cada experimento.
- [ ] Los tests de prompt injection pasan en la versión desplegada.
- [ ] La ADR del modelo final justifica la elección con números.

## Fase D — Producción y portfolio (etapas 10 a 12, unas 2,5 semanas)

Al final de la Fase D tenés una demo pública estable, monitoreada, con backups probados y un repositorio que se explica solo en una entrevista.

### Etapa 10 — Observabilidad y analíticas (1 semana)

Objetivo: ver qué pasa dentro del sistema y mostrarlo en un dashboard.

- Métricas de la API con `prometheus-fastapi-instrumentator`, más métricas propias del pipeline y del RAG.
- Prometheus con retención corta (7 a 15 días) para cuidar disco y RAM; exportadores de nodo, PostgreSQL y Celery.
- Grafana detrás de Cloudflare Access, nunca expuesto directo.
- Dashboard con: tiempo de procesamiento por página, errores de extracción y OCR, tiempo de embeddings, latencia de búsqueda, tiempo hasta el primer token, tokens por segundo, CPU y RAM, tasa de citas válidas.
- Alertas gratuitas de Grafana por email o Telegram: API caída, cola de trabajos creciendo, RAM sobre 90 %.
- Módulo de analíticas para admins de cada organización: documentos procesados, preguntas por día y **preguntas sin respuesta** (revelan qué documentos faltan cargar).
- Opcional: trazas con OpenTelemetry y errores con GlitchTip.

Terminado cuando:

- [ ] Una pregunta lenta se puede diagnosticar en el dashboard: búsqueda, cola o generación.
- [ ] Una alerta de prueba llega a tu teléfono.

### Etapa 11 — Producción robusta (3 a 5 días)

Objetivo: que el sistema sobreviva a un error tuyo, a un disco lleno o a la pérdida del VPS.

- Backups diarios cifrados con restic hacia Cloudflare R2: volcado de PostgreSQL y archivos de documentos, con retención de 7 diarios y 4 semanales.
- Límites de CPU y memoria, healthchecks y reinicio automático en todos los contenedores (Quadlet con systemd si querés aprenderlo).
- Rotación de logs, cabeceras de seguridad en Caddy y reglas de rate limiting en Cloudflare.
- Runbook en `docs/operations/`: deploy, rollback a la imagen anterior, restauración de backup, rotación de secretos.

Terminado cuando:

- [ ] Restauraste la base y los archivos en un entorno limpio siguiendo solo el runbook.
- [ ] Un rollback a la versión anterior lleva menos de 5 minutos.

### Etapa 12 — Entrega de portfolio y demo pública (1 semana)

Objetivo: que un reclutador entienda el proyecto en 2 minutos y un entrevistador técnico encuentre profundidad en 20.

- README con diagrama de arquitectura, GIF de la demo, stack, cómo correrlo en local y enlaces a ADRs y métricas.
- Organización demo con documentos públicos de ejemplo y cuenta de solo lectura que se resetea cada noche; límites de uso más estrictos para la demo y Turnstile en el acceso.
- Video de 3 minutos con el recorrido completo.
- Artículo técnico: arquitectura, decisiones, resultados de la evaluación y qué cambiarías con GPU.
- Release `v1.0.0` con changelog.

Terminado cuando:

- [ ] Alguien ajeno al proyecto entra a la demo y obtiene una respuesta citada sin ayuda.
- [ ] El README responde: qué es, cómo funciona, cómo se probó y cómo se despliega.

### Extensiones opcionales después de la v1

- **Integración con Dolibarr**: un conector que ingiere documentos del gestor documental (ECM) de Dolibarr 20 vía su API REST y responde preguntas sobre facturas, contratos o pedidos. Aprovecha tu experiencia y es un diferencial fuerte.
- Servidor MCP que expone la búsqueda de DocuMind a asistentes de IA.
- Más formatos (XLSX, imágenes con OCR, correos).
- Almacenamiento S3 compatible con MinIO o Garage, gracias a la interfaz de la etapa 4.

## Calendario, hitos y riesgos

Con dedicación constante, la v1.0 está lista en unas **14 semanas**: algo más que las 10 a 12 del plan original, porque suma el dimensionamiento inicial, el dataset de evaluación y la puesta en producción robusta.

&#91;embedded content: hoja de ruta · 4 fases, 13 etapas, 4 hitos\]

Cada hito es un punto de control: si sus criterios de terminado no se cumplen, no se pasa a la fase siguiente.

### Riesgos principales

| Riesgo | Señal de alerta | Mitigación |
| --- | --- | --- |
| El VPS no alcanza para el LLM | Ollama se reinicia, swap alto, RAM sobre 90 % | Modelo más chico, 1 tarea por worker, Grafana apagado hasta la etapa 10 |
| Respuestas demasiado lentas en CPU | Más de 30 s hasta completar una respuesta | Contexto más corto, abstención sin LLM, streaming y cola visible |
| Alcance que crece sin control | Una etapa dura más del doble de lo estimado | Cerrar con lo mínimo de "terminado" y pasar extras a un backlog |
| Fuga de datos entre organizaciones | Falla un test de aislamiento | RLS más tests en CI; revisar cada consulta nueva |
| Código generado que no entendés | No podés explicarlo en voz alta | Revisar cada diff y escribir vos las piezas clave: chunking, fusión de rankings, validación de citas |
| OCR lento o de mala calidad | Mucho tiempo por página o texto ilegible | OCR solo en páginas sin texto, límite de páginas, cola de baja prioridad |
| Pérdida de datos | Disco lleno o VPS caído | Backups cifrados en R2 y restauración probada (etapa 11) |
| Cambios en planes gratuitos | Aviso de cambio de condiciones | Solo Cloudflare y GitHub son externos; todo lo demás es self-hosted y reemplazable |
