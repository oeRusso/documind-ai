# Etapa 9 — Evaluación continua y seguridad de IA

- **Fase:** C — Inteligencia (cierra con el tag `v0.3.0`)
- **Duración estimada:** 1,5 semanas
- **Rama:** `development` (PR a `main` al cerrar la etapa)
- **Estado:** terminada (2026-11-15), en `development`

## Objetivo

Convertir "parece que anda" en números, y blindar el sistema contra documentos maliciosos.

## Tareas

- [x] Suite de evaluación: recall@k y MRR (recuperación), tasa de citas válidas, tasa de abstención correcta en preguntas sin respuesta. La de recuperación corre en CI; la completa, con LLM, corre en local con la RX 6600.
- [x] Set de prompt injection (en `tests/security/`): documentos con instrucciones ocultas ("ignorá tus reglas", texto blanco sobre blanco, links a sitios externos). El modelo no debe obedecerlas.
- [x] Salida segura en el frontend: Markdown sin HTML crudo y sin cargar imágenes ni links externos automáticamente.
- [x] Experimentos que solo se quedan si mejoran las métricas: reranking con un cross-encoder multilingüe (medir la latencia en CPU), Docling para documentos con tablas, ajuste del tamaño de los fragmentos.
- [x] Seguridad del código en CI: Bandit, pip-audit y Trivy sobre las imágenes.

## Fuera de alcance

- Fine-tuning de modelos (backlog).
- Prometheus, Grafana y dashboards (etapa 10).
- Dejar un experimento que no mejoró las métricas: se documenta y se descarta.

## Criterios de terminado

- [x] `docs/evaluation/` tiene un informe con métricas antes y después de cada experimento.
- [ ] Los tests de prompt injection pasan en la versión desplegada. **En local 8/8; contra el VPS se corre `eval_injection --base` en el despliegue final.**
- [x] La ADR del modelo final justifica la elección con números.

## Notas

- Dónde va cada cosa: código de métricas en `backend/app/ai/evaluation/`, dataset y scripts en `backend/evaluation/`, informes en `docs/evaluation/`.
- Al cerrar esta etapa termina la Fase C: tag `v0.3.0`.

- **Lo que deja la etapa 8** (ver su "Resultado" y la ADR 0010): conversaciones guardadas, preguntas de
  seguimiento (la pregunta anterior entra al prompt como `<pregunta_anterior>`, también defendida contra
  etiquetas falsas) y respuestas «no útil» exportables con `app.jobs.export_feedback`. La web muestra
  las respuestas como texto plano (sin HTML): el Markdown seguro es de esta etapa.

## Resultado

**Criterios:** informes antes y después en `docs/evaluation/` (ADR 0011); prompt injection 8/8 en local
(falta correrlo contra lo desplegado); el modelo sigue siendo `llama3.2:3b` (ADR 0009, re-medido con las defensas).

**Qué quedó:**

- **Texto oculto:** el lector de PDF descarta texto blanco, transparente o de menos de 1 punto
  (`is_hidden_span`) y loguea `hidden_text_dropped`. La capa de OCR no se filtra.
- **Prompt:** `DATA_REMINDER` repite, justo antes de la pregunta, que los fragmentos son datos.
- **`OutputGuard`** (`knowledge/domain/output_guard.py`): saca HTML e imágenes Markdown del stream,
  antes del filtro de citas; loguea `unsafe_output_removed`.
- **Set de ataques** (`evaluation/injection.py`, 8 casos) con tests sin modelo en CI y
  `evaluation.eval_injection` con el modelo real, por HTTP (sirve contra el VPS).
- **Web:** Markdown propio (`lib/markdown.ts`, `features/chat/answer-markdown.tsx`): listas, negrita,
  código y citas; links como texto con su dominio; imágenes «omitidas»; nunca HTML. CSP en `next.config.ts`.
- **CI:** `.github/workflows/security.yml` con Bandit, pip-audit y Trivy (desde su imagen, sin actions
  de terceros), también cada lunes.
- **Imágenes:** el backend aplica parches de Debian; la web no lleva npm ni corepack.
- **Experimentos:** tamaño de fragmentos (descartado). Reranking y Docling **descartados**: necesitan
  Hugging Face y Esteban no lo autorizó (2026-11-15).

**Pendientes:**

- Correr `eval_injection --base https://documind.esteban-russo.com` en el despliegue.
- CSP con nonces para `script-src` (hoy no se restringe: Next.js usa scripts inline).

## Referencias

- Parte 1: §7 (filas IA y Dependencias), §8 (tipos de tests, CI y métricas).
