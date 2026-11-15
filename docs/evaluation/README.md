# Evaluación

La suite que dice si DocuMind responde bien. Los scripts están en `backend/evaluation/`, el código de
métricas en `backend/app/ai/evaluation/` y acá los informes (generados, no se editan a mano).

| Qué mide | Script (en `backend/`) | Dónde corre | Último informe |
|---|---|---|---|
| Búsqueda: recall@5, recall@10, MRR, latencia | `uv run python -m evaluation.eval_retrieval` | CI (solo modo texto, con piso 0,55) y local completo | [retrieval-2026-11-11](retrieval-2026-11-11.md) |
| Respuestas: responde, cita la página correcta, citas inválidas, abstención correcta, velocidad, RAM | `OLLAMA_URL=http://127.0.0.1:11435 uv run python -m evaluation.eval_answers` | local (~40 min) | [answers-2026-11-15](answers-2026-11-15.md) |
| Preguntas de seguimiento | `uv run python -m evaluation.eval_followups` | local | [followups-2026-11-15](followups-2026-11-15.md) |
| Prompt injection con el modelo real | `uv run python -m evaluation.eval_injection [--base URL]` | local y contra lo desplegado | [injection-2026-11-15](injection-2026-11-15.md) |
| Varias preguntas a la vez | `uv run python -m evaluation.load_chat` | local / VPS | (sale por consola) |

Los tests de prompt injection sin modelo están en `backend/tests/security/test_prompt_injection.py` y
`backend/tests/integration/test_prompt_injection_api.py`, y corren en CI.

Experimentos (se quedan solo si mejoran una métrica): tamaño de fragmentos
([300](retrieval-2026-11-15-chunks300.md), [600](retrieval-2026-11-15-chunks600.md): descartado), ver ADR 0011.
