# Evaluación de búsqueda — 2026-11-15 (fragmentos de 600 tokens)

Generado por `uv run python -m evaluation.eval_retrieval` (etapa 6). No editar a mano.

- Corpus: 12 leyes de Infoleg, 341 fragmentos.
- Preguntas: 68 con respuesta y 11 sin respuesta.
- Un resultado es relevante si es el documento esperado y sus páginas incluyen la página esperada.
- Latencia: búsqueda completa (incluye calcular el embedding de la pregunta), en la PC de desarrollo.

| Modo | recall@5 | recall@10 | MRR | p50 ms | p95 ms |
|---|---|---|---|---|---|
| text | 0.662 | 0.809 | 0.455 | 12 | 14 |
| vector (bge-m3) | 0.897 | 0.956 | 0.732 | 42 | 45 |
| hybrid (bge-m3) | 0.897 | 0.912 | 0.709 | 55 | 60 |

Por tipo de pregunta (recall@5 / MRR):

| Modo | keywords | natural |
|---|---|---|
| text | 0.625 / 0.429 | 0.667 / 0.459 |
| vector (bge-m3) | 0.750 / 0.469 | 0.917 / 0.767 |
| hybrid (bge-m3) | 0.875 / 0.667 | 0.900 / 0.715 |

`natural`: preguntas en lenguaje cotidiano. `keywords`: términos exactos o números de artículo, como también se busca.

Puntaje del primer resultado (mediana), con y sin respuesta en el corpus. En modo vector es la similitud coseno; en texto, el rango de PostgreSQL; en híbrido, el puntaje propio del método que trajo ese fragmento. Sirve para elegir el umbral de «no encontré» de la etapa 7:

| Modo | con respuesta | sin respuesta |
|---|---|---|
| text | 0.7059 | 0.4737 |
| vector (bge-m3) | 0.6351 | 0.4911 |
| hybrid (bge-m3) | 0.6139 | 0.4601 |

Preguntas fuera del top 5 por modo:

- **text**: q002, q004, q005, q010, q011, q013, q014, q019, q026, q027, q028, q029, q035, q037, q040, q042, q050, q053, q055, q056, q072, q076, q077
- **vector (bge-m3)**: q014, q016, q027, q038, q054, q072, q076
- **hybrid (bge-m3)**: q010, q013, q014, q026, q027, q056, q072
