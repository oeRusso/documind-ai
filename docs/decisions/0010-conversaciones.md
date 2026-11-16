# 0010 — Conversaciones: privacidad, preguntas de seguimiento y guardado de respuestas

- **Estado:** aceptada
- **Fecha:** 2026-11-15
- **Etapa:** 08

## Contexto

La etapa 7 respondía sin estado: la pregunta, la respuesta y las citas solo viajaban por SSE y a los
logs. La etapa 8 guarda conversaciones, mensajes y citas, y permite preguntas de seguimiento
(«¿y cuándo es válida?»). Hay que decidir tres cosas:

1. Quién ve una conversación.
2. Con qué texto se busca una pregunta de seguimiento.
3. Cómo se guarda una respuesta que tarda hasta un minuto en generarse, y que la persona puede cortar.

## Opciones consideradas

**Privacidad**
1. **Conversaciones de la organización** (cualquier miembro ve las de todos): más simple, pero expone
   lo que cada persona pregunta.
2. **Conversaciones de cada persona dentro de la organización**: cada consulta filtra por
   `organization_id` **y** `user_id`; la de otro miembro es 404, como un recurso de otra organización.

**Texto de búsqueda en un seguimiento** (medido con `evaluation/eval_followups.py`)
1. Solo la pregunta actual (`none`).
2. Pregunta anterior + actual, siempre (`always`).
3. Pregunta anterior + actual solo si la actual es corta (`short`).
4. Reformular con el LLM: una llamada extra al modelo antes de cada búsqueda (10–20 s más en CPU).
   No se implementó: solo entraría si mejora la métrica, y `short` ya resuelve la mayoría.

**Guardado de la respuesta**
1. Guardar todo al final, en la transacción del pedido: se pierde la pregunta si la persona corta, y
   la transacción quedaría abierta mientras genera el modelo.
2. **Guardar la pregunta y una respuesta vacía (`streaming`) antes de generar, y completarla al final
   en una transacción corta propia** (`AnswerRecorder`), también al detener (`stopped`) o si el modelo
   falla (`failed`).

## Decisión

- Conversaciones **privadas de cada persona**. RLS sigue siendo por organización (segunda capa); el
  filtro por persona está en las consultas.
- Seguimientos con **`short` de hasta 6 palabras**: la pregunta anterior se suma a la búsqueda y se le
  pasa al modelo como `<pregunta_anterior>`, solo como contexto.
- Respuesta guardada en **dos tiempos** (opción 2). La transacción del pedido se commitea dentro de la
  dependencia `prepare_message`, antes de abrir el stream: FastAPI arranca el generador del SSE en
  una tarea propia *antes* de cerrar las dependencias, y sin ese commit la respuesta podía terminar
  antes de que existiera la fila (pasó en los tests: 1 de cada 4 corridas).

## Consecuencias

- Un admin no puede ver lo que preguntan los demás. Las métricas por organización (etapa 10) se
  sacan agregadas, sin mostrar conversaciones ajenas.
- Una respuesta que quedó en `streaming` significa que el proceso murió a mitad de camino; la web la
  muestra como «interrumpida».
- Las citas guardan título, páginas, extracto e ids de los fragmentos. Si el documento se purga,
  `document_id` queda en NULL y la cita sigue legible.
- `short` pierde una de 30 preguntas cuando la persona cambia de tema con una pregunta corta. Si el
  dataset de seguimientos crece, se puede volver a medir la reformulación con el LLM o buscar con las
  dos versiones y fusionarlas con RRF.
- Las respuestas marcadas «no útil» se exportan con `python -m app.jobs.export_feedback` para
  revisarlas a mano; no entran solas al dataset (una respuesta mala no es una etiqueta buena).

## Evidencia

[docs/evaluation/followups-2026-11-15.md](../evaluation/followups-2026-11-15.md): 22 seguimientos y
30 cambios de tema, búsqueda híbrida con `bge-m3`.

| Estrategia | seguimiento recall@5 | cambio de tema recall@5 |
|---|---|---|
| none | 0,455 | 0,900 |
| always | 0,682 | 0,467 |
| short (≤4) | 0,455 | 0,900 |
| **short (≤6)** | **0,727** | **0,867** |
| short (≤8) | 0,682 | 0,750 |
