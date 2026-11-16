# Etapa 6 — Dataset de evaluación, embeddings y búsqueda híbrida

- **Fase:** C — Inteligencia
- **Duración estimada:** 1,5 semanas
- **Rama:** `development` (PR a `main` al cerrar la etapa)
- **Estado:** terminada (2026-11-11), en `development`.

## Objetivo

Recuperar los fragmentos correctos, y poder medirlo, antes de que intervenga ningún LLM.

## Tareas

- [x] **Primero el dataset** (en `backend/evaluation/`): 10 a 20 documentos públicos en español (normativa, manuales, contratos modelo) y 50 a 100 preguntas con documento y página esperados. Incluir un 15 % de preguntas sin respuesta en los documentos.
- [x] Interfaz `EmbeddingProvider` (en `app/ai/providers/`) con implementación en Ollama o FastEmbed; comparar dos modelos multilingües (p. ej. bge-m3).
- [x] Tabla `embeddings` con nombre y versión del modelo, para poder reindexar al cambiarlo; índice HNSW de pgvector.
- [x] Agregar la etapa `embedding` al pipeline (`chunking` → `embedding` → `ready`).
- [x] Búsqueda de texto completo de PostgreSQL con configuración en español y `unaccent`, índice GIN.
- [x] Fusión de ambos rankings con Reciprocal Rank Fusion; el filtro por organización y por documentos se aplica dentro de la consulta, nunca después.
- [x] Endpoint `/api/v1/search` y página de búsqueda en el frontend.
- [x] Script `eval_retrieval` que calcula recall@5 y MRR sobre el dataset, corriendo en CI.

## Fuera de alcance

- LLM, generación de respuestas y prompts (etapa 7).
- Reranking con cross-encoder (etapa 9, solo si mejora métricas).
- Fijar el modelo de LLM: se elige en la etapa 7.
- Búsqueda entre organizaciones (backlog: no se hace nunca en v1).

## Criterios de terminado

- [x] Tenés recall@5 y MRR medidos para búsqueda vectorial, textual e híbrida, y la comparación está en una ADR.
- [x] Una búsqueda responde en menos de 300 ms con todos tus documentos de prueba cargados.

## Notas

- La Parte 2 dice `/search`; por la convención de la §9 queda como `/api/v1/search`.
- La tabla de servicios ubica Hugging Face Hub en la etapa 5, pero recién se usa acá (FastEmbed baja modelos de HF; Ollama usa su propio registro).
- **Fusión de rankings (RRF)**: pieza clave para escribir vos.
- Variables de entorno que entran: `OLLAMA_URL`, `EMBEDDING_MODEL` (su valor sale de esta etapa).

## Resultado

**Criterios de terminado: los dos cumplidos.**

1. recall@5 y MRR medidos para búsqueda vectorial, textual e híbrida, con dos modelos, y comparados en la
   ADR 0008. Ganó **bge-m3 + híbrido**: recall@5 de 0,912, y 1,000 en búsquedas por términos exactos.
2. Una búsqueda responde en menos de 300 ms: el p95 fue 95 ms con todo el corpus cargado, y 51 ms
   por la API.

**Qué quedó:**

- **Dataset:** `backend/evaluation/` con 12 leyes de Infoleg (textos oficiales de acceso libre, con su
  origen y la fecha de descarga en el manifest) y 79 preguntas. La página esperada se calcula sola y la
  verifica un test.
- **Embeddings:** `app/ai/providers/` (`EmbeddingProvider` y su implementación con Ollama) y un contenedor
  `ollama` en el compose.
- **Base de datos:** `chunk_embeddings` con un índice HNSW por modelo, y búsqueda de texto en español sin
  tildes (migración 0006).
- **Pipeline:** se agregó el paso `embedding`.
- **Búsqueda:** módulo `knowledge` (por significado, por palabras e híbrida con RRF) y la ruta
  `GET /api/v1/search`.
- **Web:** página **Búsqueda** con los términos resaltados.
- **Medición:** `evaluation/eval_retrieval.py`; el CI corre el modo palabras con un piso de calidad.
- **Números:** 473 tests de backend y 35 de frontend.

**Problemas encontrados:**

- La migración 0006 falló por la convención de nombres de constraints (se corrigió con `op.f`). Al
  encadenar comandos se corrió un downgrade en la base de desarrollo, que borró los fragmentos locales. Se
  reprocesaron con el botón Reprocesar.
- El Ollama del sistema solo escucha en `127.0.0.1` y los contenedores no lo alcanzan. Se usa un
  contenedor propio, y los modelos quedaron duplicados en disco (~1,8 GB): los del sistema se pueden borrar.

**Pendientes:**

- Etapa 9: mejorar la búsqueda por palabras solo si mueve las métricas (títulos "Art. N." como sección,
  RRF con pesos) y ampliar las preguntas por términos exactos.
- Etapa 7: usar la distribución de puntajes de las preguntas sin respuesta (en el informe) para elegir el
  umbral de "no encontré evidencia".
- Documentos procesados antes de esta etapa no tienen embeddings: hay que tocar "Reprocesar".

## Referencias

- Parte 1: §5 (tabla `embeddings`), §6 (flujo de una pregunta, pasos 2 a 4), §8 (evaluación en CI).
