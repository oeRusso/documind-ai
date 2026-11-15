# Preguntas de seguimiento — 2026-11-15

Generado por `uv run python -m evaluation.eval_followups` (etapa 8). No editar a mano.

Qué texto se busca cuando hay una pregunta anterior en la conversación. Búsqueda híbrida con `bge-m3`, el mismo corpus de la etapa 6.

- **Seguimiento** (22 preguntas, `evaluation/followups.json`): «¿Y cuándo es válida?» después de «¿Qué es la firma digital?». Solas no dicen de qué hablan.
- **Cambio de tema** (60 preguntas): cada pregunta natural del dataset, hecha después de una pregunta sobre otra ley. Ahí la pregunta anterior solo puede estorbar.

| Estrategia | seguimiento recall@5 | seguimiento MRR | cambio de tema recall@5 | cambio de tema MRR |
|---|---|---|---|---|
| none | 0.455 | 0.330 | 0.900 | 0.708 |
| always | 0.682 | 0.512 | 0.467 | 0.320 |
| short (≤4 palabras) | 0.455 | 0.368 | 0.900 | 0.708 |
| short (≤6 palabras) | 0.727 | 0.547 | 0.867 | 0.668 |
| short (≤8 palabras) | 0.682 | 0.493 | 0.750 | 0.553 |
| short (≤10 palabras) | 0.682 | 0.524 | 0.633 | 0.449 |
| short (≤12 palabras) | 0.682 | 0.512 | 0.500 | 0.345 |

Preguntas de seguimiento fuera del top 5:

- **none**: f03, f06, f07, f08, f09, f10, f11, f12, f14, f15, f21, f22
- **always**: f01, f05, f06, f07, f10, f11, f12
- **short (≤4 palabras)**: f03, f06, f07, f08, f09, f10, f11, f12, f14, f15, f21, f22
- **short (≤6 palabras)**: f06, f07, f10, f11, f12, f15
- **short (≤8 palabras)**: f01, f05, f06, f07, f10, f11, f12
- **short (≤10 palabras)**: f01, f05, f06, f07, f10, f11, f12
- **short (≤12 palabras)**: f01, f05, f06, f07, f10, f11, f12
