# Etapa 6 — Dataset de evaluación, embeddings y búsqueda híbrida

- **Fase:** C — Inteligencia
- **Duración estimada:** 1,5 semanas
- **Rama:** `development` (PR a `main` al cerrar la etapa)
- **Estado:** pendiente

## Objetivo

Recuperar los fragmentos correctos, y poder medirlo, antes de que intervenga ningún LLM.

## Tareas

- [ ] **Primero el dataset** (en `backend/evaluation/`): 10 a 20 documentos públicos en español (normativa, manuales, contratos modelo) y 50 a 100 preguntas con documento y página esperados. Incluir un 15 % de preguntas sin respuesta en los documentos.
- [ ] Interfaz `EmbeddingProvider` (en `app/ai/providers/`) con implementación en Ollama o FastEmbed; comparar dos modelos multilingües (p. ej. bge-m3).
- [ ] Tabla `embeddings` con nombre y versión del modelo, para poder reindexar al cambiarlo; índice HNSW de pgvector.
- [ ] Agregar la etapa `embedding` al pipeline (`chunking` → `embedding` → `ready`).
- [ ] Búsqueda de texto completo de PostgreSQL con configuración en español y `unaccent`, índice GIN.
- [ ] Fusión de ambos rankings con Reciprocal Rank Fusion; el filtro por organización y por documentos se aplica dentro de la consulta, nunca después.
- [ ] Endpoint `/api/v1/search` y página de búsqueda en el frontend.
- [ ] Script `eval_retrieval` que calcula recall@5 y MRR sobre el dataset, corriendo en CI.

## Fuera de alcance

- LLM, generación de respuestas y prompts (etapa 7).
- Reranking con cross-encoder (etapa 9, solo si mejora métricas).
- Fijar el modelo de LLM: se elige en la etapa 7.
- Búsqueda entre organizaciones (backlog: no se hace nunca en v1).

## Criterios de terminado

- [ ] Tenés recall@5 y MRR medidos para búsqueda vectorial, textual e híbrida, y la comparación está en una ADR.
- [ ] Una búsqueda responde en menos de 300 ms con todos tus documentos de prueba cargados.

## Notas

- La Parte 2 dice `/search`; por la convención de la §9 queda como `/api/v1/search`.
- La tabla de servicios ubica Hugging Face Hub en la etapa 5, pero recién se usa acá (FastEmbed baja modelos de HF; Ollama usa su propio registro).
- **Fusión de rankings (RRF)**: pieza clave para escribir vos.
- Variables de entorno que entran: `OLLAMA_URL`, `EMBEDDING_MODEL` (su valor sale de esta etapa).

## Referencias

- Parte 1: §5 (tabla `embeddings`), §6 (flujo de una pregunta, pasos 2 a 4), §8 (evaluación en CI).
