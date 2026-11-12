# Etapa 8 — Conversaciones y experiencia de chat

- **Fase:** C — Inteligencia
- **Duración estimada:** 1 semana
- **Rama:** `development` (PR a `main` al cerrar la etapa)
- **Estado:** pendiente

## Objetivo

La demo central del portfolio, de punta a punta.

## Tareas

- [ ] Tablas `conversations`, `messages` y `citations` (con `organization_id` y RLS); historial por usuario y organización. Las citas que en la etapa 7 solo viajaban por SSE pasan a persistirse.
- [ ] Preguntas de seguimiento: la consulta de búsqueda combina la pregunta actual con el último turno. Reformular con el LLM solo si el dataset muestra mejora.
- [ ] Alcance de la conversación (`scope`): todos los documentos de la organización o una selección.
- [ ] Interfaz: chat con streaming, panel de citas con el fragmento resaltado y visor PDF (pdf.js) abierto en la página citada.
- [ ] Botones "útil / no útil" por respuesta; las marcadas como no útiles alimentan el dataset.

## Fuera de alcance

- Suite de evaluación continua y prompt injection (etapa 9).
- Analíticas por organización (etapa 10).
- Aplicación móvil nativa (backlog).

## Criterios de terminado

- [ ] El recorrido subir documento → preguntar → hacer clic en la cita → ver la página funciona en producción.
- [ ] Un viewer puede consultar pero no subir ni borrar documentos.

## Notas

- **Decisión sobre `citations`** (tomada en la etapa 0): las tres tablas se crean acá, no en la etapa 7 como dice la Parte 1 (§5).
- **Lo que deja la etapa 7** (ver su "Resultado" y la ADR 0009): `AnswerQuestion` en `knowledge`, con
  `prepare` y `stream`, el filtro de citas, la cola de generación y `POST /api/v1/chat` sin estado.
  `conversations` lo usa por la capa `application`: guarda la pregunta, la respuesta y las `Citation`
  que hoy solo van al evento SSE y a los logs. Las preguntas de seguimiento combinan la pregunta con el
  último turno antes de `prepare`. La página `/ask` pasa a ser el chat con historial.

## Referencias

- Parte 1: §5 (tablas de la etapa 8 y `citations`), §6 (paso 1 del flujo y contrato de respuesta).
