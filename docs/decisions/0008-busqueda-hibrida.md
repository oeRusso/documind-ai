# 0008 — Búsqueda: modelo de embeddings y modo híbrido

- **Estado:** aceptada
- **Fecha:** 2026-11-11
- **Etapa:** 06

## Contexto

Para responder con citas (etapa 7) primero hay que encontrar los fragmentos correctos. Hay dos maneras
de buscar: por **significado** (embeddings: "me echaron" encuentra "despido") y por **palabras**
(búsqueda de texto de PostgreSQL: encuentra "art. 245" o "ley 11.544" tal cual). Hay que elegir el
modelo de embeddings y cómo combinar las dos, con números y no a ojo. Restricciones: todo local con
Ollama, CPU sin GPU, VPS con 8 GB compartidos, menos de 300 ms por búsqueda.

## Opciones consideradas

Modelos (los dos multilingües, gratuitos y disponibles en Ollama):

1. **bge-m3** (1024 dimensiones, ~1,2 GB).
2. **paraphrase-multilingual** (768 dimensiones, ~560 MB): más liviano.

Modos:

1. **Solo significado.**
2. **Solo palabras.**
3. **Híbrido**: los dos rankings fusionados con Reciprocal Rank Fusion (k = 60).

## Decisión

**bge-m3 + modo híbrido por defecto.**

Medido con `python -m evaluation.eval_retrieval` sobre 12 leyes argentinas (Infoleg, 418 fragmentos) y 79
preguntas (68 con respuesta, de las cuales 60 son en lenguaje cotidiano y 8 son por términos exactos):

| Modo | recall@5 | MRR | términos exactos (recall@5) | p95 |
|---|---|---|---|---|
| palabras | 0,618 | 0,425 | 0,500 | 8 ms |
| significado, bge-m3 | 0,912 | 0,771 | 0,875 | 83 ms |
| **híbrido, bge-m3** | **0,912** | 0,712 | **1,000** | 95 ms |
| significado, paraphrase | 0,750 | 0,558 | 0,375 | 75 ms |
| híbrido, paraphrase | 0,838 | 0,621 | 0,625 | 78 ms |

- bge-m3 le gana a paraphrase-multilingual en todos los modos: +16 puntos de recall@5 en significado.
- Con bge-m3, híbrido y significado empatan en recall@5 (0,912), pero el híbrido es el único que encuentra
  todas las búsquedas por términos exactos. Como el chat (etapa 7) va a leer los primeros 5 fragmentos,
  importa más estar en los 5 (recall@5) que estar primero (MRR, donde gana significado: 0,771 contra 0,712).
- Todos los modos responden en menos de 100 ms (p95), lejos del límite de 300 ms. Por la API, una búsqueda
  completa tardó 51 ms.

Detalles de implementación:

- `chunk_embeddings` guarda un vector por fragmento **y por modelo**: cambiar de modelo es reindexar sin
  perder el anterior. Hay un índice HNSW por modelo, con la columna convertida al tamaño de ese modelo.
- El filtro por organización y por documentos va **dentro** de las consultas. pgvector 0.8 sigue
  recorriendo el índice si el filtro descarta resultados (`hnsw.iterative_scan = relaxed_order`).
- La búsqueda por palabras usa la configuración `documind_es`: español con raíces ("plazos" → "plazo") y
  sin tildes. Las preguntas se convierten a OR de sus palabras y el rango premia a los fragmentos que
  tienen más de ellas.
- Se embebe "sección + texto" de cada fragmento.
- `SqlChunkSearch` (módulo `knowledge`) es el único lugar que lee tablas de otros módulos (fragmentos,
  embeddings y títulos de documentos) en una sola consulta. Es de solo lectura; separarla en varias
  consultas obligaría a filtrar después y rompería la regla de filtrar dentro de la consulta.
- Ollama corre como contenedor del compose (`ollama/ollama:0.40.12`, `mem_limit 3g`, descarga el modelo
  de la RAM a los 10 minutos sin uso).

## Consecuencias

- RAM: bge-m3 ocupa ~1,3 GB cuando está cargado. En el VPS (8 GB compartidos) va a convivir con el LLM de la
  etapa 7. Si no entran juntos, paraphrase-multilingual es el plan B medido (recall@5 de 0,838 en híbrido).
- La búsqueda por palabras sola es floja (0,618). Hay candidatos a mejorar, pero según la regla "medir
  antes de optimizar" entran solo si mueven las métricas (etapa 9):
  - detectar "Art. 150. —Licencia ordinaria." como título (hoy la sección queda en "CAPITULO I");
  - RRF con pesos.
- El CI no tiene Ollama: corre la evaluación solo en modo palabras, con un piso de recall@5 de 0,55. La
  comparación completa se corre localmente y se commitea en `docs/evaluation/`. Sumar Ollama al CI
  (imagen de 3,4 GB y modelo en cada corrida) queda para cuando haga falta.
- Las 8 preguntas por términos exactos son pocas: la ventaja del híbrido ahí es una señal, no una prueba.
  Ampliar ese grupo en la etapa 9.

## Evidencia

- `docs/evaluation/retrieval-2026-11-11.md` y `backend/evaluation/results/retrieval.json`.
- Dataset: `backend/evaluation/` (corpus con su origen en `corpus/manifest.json`, preguntas en
  `questions.json`, verificadas por `tests/unit/test_evaluation_dataset.py`).
