# Etapa 7 — RAG con citas y streaming

- **Fase:** C — Inteligencia
- **Duración estimada:** 1,5 semanas
- **Rama:** `development` (PR a `main` al cerrar la etapa)
- **Estado:** pendiente

## Objetivo

Respuestas fundamentadas, con citas verificables, que digan "no lo sé" cuando corresponde.

## Tareas

- [ ] Interfaz `LLMProvider` con implementación en Ollama; elegir el modelo con los datos de la etapa 0 y del dataset.
- [ ] Prompt con reglas fijas: responder solo con el contexto, citar con marcadores `[n]` y declarar falta de evidencia. Los fragmentos van delimitados y marcados como datos, no como instrucciones. Responder en el idioma de la pregunta.
- [ ] Constructor de contexto con presupuesto de tokens (los modelos chicos rinden mejor con contextos cortos) y unión de fragmentos contiguos.
- [ ] Si la mejor coincidencia queda bajo un umbral (`RAG_MIN_SCORE`), se responde "no encontré evidencia" **sin llamar al LLM**.
- [ ] Validación de citas: cada `[n]` debe apuntar a un fragmento entregado; las inválidas se descartan y se registran.
- [ ] Streaming con Server-Sent Events de FastAPI a Next.js: eventos `token`, `citations` y `done` (contrato de la Parte 1, §6).
- [ ] Semáforo de generación (`LLM_MAX_CONCURRENCY`): 1 o 2 respuestas simultáneas como máximo; las demás esperan en cola y el usuario ve su posición.
- [ ] Ollama con el modelo precargado y `keep_alive` largo.
- [ ] Rate limit en el endpoint de chat.

## Fuera de alcance

- Tablas `conversations`, `messages` y `citations`, historial y preguntas de seguimiento (etapa 8).
- Visor PDF y panel de citas (etapa 8).
- Set de prompt injection y salida Markdown segura en el frontend (etapa 9).
- Reranking (etapa 9).
- Agentes que ejecutan acciones (backlog: nunca en v1).

## Criterios de terminado

- [ ] Una pregunta sin respuesta en los documentos devuelve "no encontré evidencia" y no una invención.
- [ ] Cinco preguntas simultáneas no tiran abajo el VPS: se encolan y se responden.
- [ ] Cada cita guarda documento, página y fragmento.

## Notas

- **Decisión sobre `citations`** (tomada en la etapa 0): la Parte 1 ubica la tabla `citations` en la etapa 7, pero depende de `messages`, que entra en la 8. En esta etapa, "cada cita guarda documento, página y fragmento" se cumple con el evento SSE `citations` (`document_id`, `document_title`, `page_start`, `page_end`, `excerpt`) y su registro en los logs. Las tablas se crean en la etapa 8.
- **Validación de citas**: pieza clave para escribir vos. Tests primero.
- Variables de entorno que entran: `LLM_MODEL`, `RAG_MIN_SCORE`, `LLM_MAX_CONCURRENCY`.

## Referencias

- Parte 1: §6 (flujo de una pregunta, reglas del prompt, contrato de respuesta), §7 (fila IA).
