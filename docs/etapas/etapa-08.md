# Etapa 8 — Conversaciones y experiencia de chat

- **Fase:** C — Inteligencia
- **Duración estimada:** 1 semana
- **Rama:** `development` (PR a `main` al cerrar la etapa)
- **Estado:** terminada (2026-11-15), en `development`

## Objetivo

La demo central del portfolio, de punta a punta.

## Tareas

- [x] Tablas `conversations`, `messages` y `citations` (con `organization_id` y RLS); historial por usuario y organización. Las citas que en la etapa 7 solo viajaban por SSE pasan a persistirse.
- [x] Preguntas de seguimiento: la consulta de búsqueda combina la pregunta actual con el último turno. Reformular con el LLM solo si el dataset muestra mejora.
- [x] Alcance de la conversación (`scope`): todos los documentos de la organización o una selección.
- [x] Interfaz: chat con streaming, panel de citas con el fragmento resaltado y visor PDF (pdf.js) abierto en la página citada.
- [x] Botones "útil / no útil" por respuesta; las marcadas como no útiles alimentan el dataset.

## Fuera de alcance

- Suite de evaluación continua y prompt injection (etapa 9).
- Analíticas por organización (etapa 10).
- Aplicación móvil nativa (backlog).

## Criterios de terminado

- [ ] El recorrido subir documento → preguntar → hacer clic en la cita → ver la página funciona en producción. **En local sí; en producción se verifica en el despliegue final (etapa 3).**
- [x] Un viewer puede consultar pero no subir ni borrar documentos.

## Notas

- **Decisión sobre `citations`** (tomada en la etapa 0): las tres tablas se crean acá, no en la etapa 7 como dice la Parte 1 (§5).
- **Lo que deja la etapa 7** (ver su "Resultado" y la ADR 0009): `AnswerQuestion` en `knowledge`, con
  `prepare` y `stream`, el filtro de citas, la cola de generación y `POST /api/v1/chat` sin estado.
  `conversations` lo usa por la capa `application`: guarda la pregunta, la respuesta y las `Citation`
  que hoy solo van al evento SSE y a los logs. Las preguntas de seguimiento combinan la pregunta con el
  último turno antes de `prepare`. La página `/ask` pasa a ser el chat con historial.

## Resultado

**Criterios:** el viewer pregunta pero no sube ni borra (test `test_a_viewer_asks_but_cannot_upload_or_delete_documents`).
El recorrido completo funciona en local; en producción se prueba con el despliegue final.

**Qué quedó:**

- **Módulo `conversations`** (migración `0007`, ADR 0010): `conversations`, `messages` y `citations`
  con `organization_id` y RLS. Conversaciones privadas de cada persona (la de otro miembro es 404).
  Endpoints: `POST/GET /conversations`, `GET/PATCH/DELETE /conversations/{id}`,
  `POST /conversations/{id}/messages` (SSE, con un primer evento `message` con los ids) y
  `PUT /conversations/{id}/messages/{mid}/feedback`.
- **Respuesta guardada en dos tiempos:** pregunta + respuesta vacía antes de generar; al final,
  `SqlAnswerRecorder` la completa en su propia transacción (`complete`, `stopped` o `failed`), protegida
  de la cancelación cuando la persona toca Detener.
- **Seguimientos:** `knowledge/domain/followup.py`. Se suma la pregunta anterior a la búsqueda si la
  nueva tiene hasta 6 palabras, y el modelo la recibe como `<pregunta_anterior>`. Medido con
  `evaluation/eval_followups.py` (22 seguimientos + 30 cambios de tema): recall@5 de seguimientos de
  0,455 a 0,727. La reformulación con el LLM no entró (no hizo falta medirla: costaría una llamada
  más al modelo por pregunta).
- **Útil / no útil:** `python -m app.jobs.export_feedback <organization_id>` lista las respuestas no
  útiles con lo que citaron, para que una persona las convierta en preguntas del dataset.
- **Web:** `/ask` es el chat: historial a la izquierda, alcance (todos o algunos documentos), respuesta
  en vivo, citas que abren un panel con el fragmento resaltado y la página del PDF (pdf.js, servido por
  la propia app), y botones útil / no útil. Enter manda, Shift+Enter hace salto de línea.

**Problemas encontrados:**

- **Carrera entre el stream y el commit:** FastAPI arranca el generador del SSE en una tarea propia
  antes de cerrar las dependencias. Si el modelo fallaba al instante, el guardado final llegaba antes
  que la fila. Se commitea dentro de `prepare_message` (ver ADR 0010).

**Pendientes:**

- **Etapa 3:** probar el recorrido completo en producción.
- **Etapa 9:** el Markdown seguro de las respuestas (hoy se muestran como texto plano, sin HTML).
- El visor de páginas es solo para PDF; DOCX, TXT y Markdown muestran el fragmento citado.

## Referencias

- Parte 1: §5 (tablas de la etapa 8 y `citations`), §6 (paso 1 del flujo y contrato de respuesta).
