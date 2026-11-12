# Etapa 7 — RAG con citas y streaming

- **Fase:** C — Inteligencia
- **Duración estimada:** 1,5 semanas
- **Rama:** `development` (PR a `main` al cerrar la etapa)
- **Estado:** terminada (2026-11-12), en `development`.

## Objetivo

Respuestas fundamentadas, con citas verificables, que digan "no lo sé" cuando corresponde.

## Tareas

- [x] Interfaz `LLMProvider` con implementación en Ollama; elegir el modelo con los datos de la etapa 0 y del dataset.
- [x] Prompt con reglas fijas: responder solo con el contexto, citar con marcadores `[n]` y declarar falta de evidencia. Los fragmentos van delimitados y marcados como datos, no como instrucciones. Responder en el idioma de la pregunta.
- [x] Constructor de contexto con presupuesto de tokens (los modelos chicos rinden mejor con contextos cortos) y unión de fragmentos contiguos.
- [x] Si la mejor coincidencia queda bajo un umbral (`RAG_MIN_SCORE`), se responde "no encontré evidencia" **sin llamar al LLM**.
- [x] Validación de citas: cada `[n]` debe apuntar a un fragmento entregado; las inválidas se descartan y se registran.
- [x] Streaming con Server-Sent Events de FastAPI a Next.js: eventos `token`, `citations` y `done` (contrato de la Parte 1, §6).
- [x] Semáforo de generación (`LLM_MAX_CONCURRENCY`): 1 o 2 respuestas simultáneas como máximo; las demás esperan en cola y el usuario ve su posición.
- [x] Ollama con el modelo precargado y `keep_alive` largo.
- [x] Rate limit en el endpoint de chat.

## Fuera de alcance

- Tablas `conversations`, `messages` y `citations`, historial y preguntas de seguimiento (etapa 8).
- Visor PDF y panel de citas (etapa 8).
- Set de prompt injection y salida Markdown segura en el frontend (etapa 9).
- Reranking (etapa 9).
- Agentes que ejecutan acciones (backlog: nunca en v1).

## Criterios de terminado

- [x] Una pregunta sin respuesta en los documentos devuelve "no encontré evidencia" y no una invención.
- [x] Cinco preguntas simultáneas no tiran abajo el VPS: se encolan y se responden.
- [x] Cada cita guarda documento, página y fragmento.

## Notas

- **Decisión sobre `citations`** (tomada en la etapa 0): la Parte 1 ubica la tabla `citations` en la etapa 7, pero depende de `messages`, que entra en la 8. En esta etapa, "cada cita guarda documento, página y fragmento" se cumple con el evento SSE `citations` (`document_id`, `document_title`, `page_start`, `page_end`, `excerpt`) y su registro en los logs. Las tablas se crean en la etapa 8.
- **Validación de citas**: pieza clave para escribir vos. Tests primero.
- Variables de entorno que entran: `LLM_MODEL`, `RAG_MIN_SCORE`, `LLM_MAX_CONCURRENCY`.
- **RAM del VPS compartido** (la guía del VPS compartido (ver "Despliegue" en `CLAUDE.md`)): el LLM tiene que ser de 1–3B cuantizado, con `mem_limit`.
  Un modelo de 7B no entra junto a los otros proyectos.

## Resultado

**Criterios de terminado: los tres cumplidos.**

1. **Sin evidencia, «no encontré» y no un invento.** Con `RAG_MIN_SCORE=0.5`, 6 de las 11 preguntas sin
   respuesta del dataset se responden sin llamar al modelo, y las otras 5 las rechaza el modelo mismo
   (11/11 con llama3.2:3b). Ninguna de las 68 preguntas con respuesta queda frenada por el umbral.
2. **Cinco preguntas simultáneas:** se encolaron (posiciones 3, 2, 1), todas recibieron respuesta en
   81 s y la RAM de Ollama quedó fija en 3,95 GB. Medido en la PC. En el VPS se repite en la etapa 3.
3. **Cada cita guarda documento, página y fragmento:** el evento `citations` lleva `document_id`,
   título, páginas y extracto, y el log `answer_generated` registra además los ids de los fragmentos.
   Las tablas llegan en la etapa 8.

**Qué quedó:**

- **IA:** `app/ai/providers/llm.py` (`LLMProvider`), `OllamaLLMProvider` (streaming, `keep_alive`,
  carga al arrancar) y `app/ai/concurrency.py` (`GenerationQueue`).
- **Módulo `knowledge`:** `domain/context.py` (presupuesto de tokens y unión de fragmentos contiguos),
  `domain/citations.py` (filtro de citas mientras llega el texto), `application/prompt.py`,
  `application/answer_question.py` y `presentation/chat_router.py` (`POST /api/v1/chat`, SSE, límite
  por usuario).
- **Web:** página **Preguntar** (`/ask`): texto en vivo, posición en la cola, citas como marcas que
  llevan a las fuentes y botón Detener.
- **Evaluación:** `evaluation/eval_answers.py` (umbral y comparación de modelos) y
  `evaluation/load_chat.py` (preguntas simultáneas). Informe en
  `docs/evaluation/answers-2026-11-12.md` y decisión en la ADR 0009.
- **Modelo:** `llama3.2:3b`. Citó la página correcta en 15 de 24 respuestas, contra 9 de 24 de
  `granite3.3:2b`.

**Problemas encontrados:**

- **Ollama sin memoria:** la caché de prompts de llama.cpp crece hasta 8 GB y el sistema mató el
  proceso del modelo. Se apagó con `LLAMA_ARG_CACHE_RAM=0` y Ollama quedó en 3,95 GB fijos.
- **El chat mostraba todo de golpe:** el gzip de Next.js retenía el stream hasta el final. Se resolvió
  con `compress: false`, y quedó una nota para Caddy en la etapa 3.
- **Citas con formato propio:** granite escribía `[1, Art. 92 bis]` y el filtro las descartaba. Se
  corrigió agregando al prompt un ejemplo de respuesta bien citada.
- **`podman stats` engaña:** cuenta caché de archivos y muestra el límite, no el uso real. La RAM se
  mide con `anon` del cgroup.

**Pendientes:**

- **Etapa 3:** repetir `load_chat` en el VPS, revisar `free -h` (Ollama necesita unos 4 GB) y
  configurar Caddy para que no retenga `text/event-stream`.
- **Etapa 8:** guardar conversaciones, mensajes y citas (la cola y el filtro de citas ya están listos
  para eso), y preguntas de seguimiento.
- **Etapa 9:** set de prompt injection y Markdown seguro. El prompt ya marca los fragmentos como datos
  y desactiva etiquetas falsas, pero falta medirlo. También medir si el reranking mejora las citas
  correctas: hoy 15/24 cita la página exacta, y algunas fallas son de búsqueda, no del modelo.
- **Volver a calibrar el umbral** cuando crezca el dataset.

## Referencias

- Parte 1: §6 (flujo de una pregunta, reglas del prompt, contrato de respuesta), §7 (fila IA).
