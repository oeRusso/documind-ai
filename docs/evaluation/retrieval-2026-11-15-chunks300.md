# Evaluación de búsqueda — 2026-11-15 (fragmentos de 300 tokens)

Generado por `uv run python -m evaluation.eval_retrieval` (etapa 6). No editar a mano.

- Corpus: 12 leyes de Infoleg, 603 fragmentos.
- Preguntas: 68 con respuesta y 11 sin respuesta.
- Un resultado es relevante si es el documento esperado y sus páginas incluyen la página esperada.
- Latencia: búsqueda completa (incluye calcular el embedding de la pregunta), en la PC de desarrollo.

| Modo | recall@5 | recall@10 | MRR | p50 ms | p95 ms |
|---|---|---|---|---|---|
| text | 0.574 | 0.750 | 0.368 | 6 | 10 |
| vector (bge-m3) | 0.926 | 1.000 | 0.833 | 73 | 85 |
| hybrid (bge-m3) | 0.912 | 0.956 | 0.678 | 86 | 100 |

Por tipo de pregunta (recall@5 / MRR):

| Modo | keywords | natural |
|---|---|---|
| text | 0.500 / 0.292 | 0.583 / 0.379 |
| vector (bge-m3) | 0.750 / 0.632 | 0.950 / 0.859 |
| hybrid (bge-m3) | 0.875 / 0.573 | 0.917 / 0.692 |

`natural`: preguntas en lenguaje cotidiano. `keywords`: términos exactos o números de artículo, como también se busca.

Puntaje del primer resultado (mediana), con y sin respuesta en el corpus. En modo vector es la similitud coseno; en texto, el rango de PostgreSQL; en híbrido, el puntaje propio del método que trajo ese fragmento. Sirve para elegir el umbral de «no encontré» de la etapa 7:

| Modo | con respuesta | sin respuesta |
|---|---|---|
| text | 0.6 | 0.4118 |
| vector (bge-m3) | 0.6396 | 0.5136 |
| hybrid (bge-m3) | 0.6146 | 0.459 |

Preguntas fuera del top 5 por modo:

- **text**: q002, q005, q010, q011, q013, q014, q018, q019, q026, q027, q029, q032, q033, q035, q036, q039, q040, q041, q042, q043, q051, q053, q055, q056, q059, q072, q074, q076, q077
- **vector (bge-m3)**: q014, q027, q054, q072, q073
- **hybrid (bge-m3)**: q010, q013, q014, q027, q040, q072
