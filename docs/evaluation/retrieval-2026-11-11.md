# Evaluación de búsqueda — 2026-11-11

Generado por `uv run python -m evaluation.eval_retrieval` (etapa 6). No editar a mano.

- Corpus: 12 leyes de Infoleg, 418 fragmentos.
- Preguntas: 68 con respuesta y 11 sin respuesta.
- Un resultado es relevante si es el documento esperado y sus páginas incluyen la página esperada.
- Latencia: búsqueda completa (incluye calcular el embedding de la pregunta), en la PC de desarrollo.

| Modo | recall@5 | recall@10 | MRR | p50 ms | p95 ms |
|---|---|---|---|---|---|
| text | 0.618 | 0.750 | 0.425 | 6 | 8 |
| vector (bge-m3) | 0.912 | 0.985 | 0.771 | 76 | 83 |
| hybrid (bge-m3) | 0.912 | 0.956 | 0.712 | 82 | 95 |
| vector (paraphrase-multilingual) | 0.750 | 0.882 | 0.558 | 66 | 75 |
| hybrid (paraphrase-multilingual) | 0.838 | 0.941 | 0.621 | 71 | 78 |

Por tipo de pregunta (recall@5 / MRR):

| Modo | keywords | natural |
|---|---|---|
| text | 0.500 / 0.388 | 0.633 / 0.430 |
| vector (bge-m3) | 0.875 / 0.641 | 0.917 / 0.788 |
| hybrid (bge-m3) | 1.000 / 0.744 | 0.900 / 0.708 |
| vector (paraphrase-multilingual) | 0.375 / 0.325 | 0.800 / 0.589 |
| hybrid (paraphrase-multilingual) | 0.625 / 0.422 | 0.867 / 0.648 |

`natural`: preguntas en lenguaje cotidiano. `keywords`: términos exactos o números de artículo, como también se busca.

Puntaje del primer resultado (mediana), con y sin respuesta en el corpus:

| Modo | con respuesta | sin respuesta |
|---|---|---|
| text | 0.6667 | 0.4444 |
| vector (bge-m3) | 0.6397 | 0.489 |
| hybrid (bge-m3) | 0.6107 | 0.457 |
| vector (paraphrase-multilingual) | 0.6612 | 0.51 |
| hybrid (paraphrase-multilingual) | 0.6287 | 0.4544 |

Preguntas fuera del top 5 por modo:

- **text**: q002, q004, q005, q010, q011, q013, q014, q019, q026, q027, q028, q029, q033, q035, q037, q040, q042, q050, q053, q055, q056, q059, q072, q074, q076, q077
- **vector (bge-m3)**: q013, q014, q027, q035, q054, q075
- **hybrid (bge-m3)**: q002, q010, q013, q014, q027, q056
- **vector (paraphrase-multilingual)**: q014, q016, q019, q027, q032, q035, q037, q038, q042, q051, q052, q054, q072, q073, q074, q076, q078
- **hybrid (paraphrase-multilingual)**: q013, q014, q016, q019, q027, q053, q054, q056, q073, q076, q078
