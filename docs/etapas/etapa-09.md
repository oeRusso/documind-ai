# Etapa 9 — Evaluación continua y seguridad de IA

- **Fase:** C — Inteligencia (cierra con el tag `v0.3.0`)
- **Duración estimada:** 1,5 semanas
- **Rama:** `development` (PR a `main` al cerrar la etapa)
- **Estado:** pendiente

## Objetivo

Convertir "parece que anda" en números, y blindar el sistema contra documentos maliciosos.

## Tareas

- [ ] Suite de evaluación: recall@k y MRR (recuperación), tasa de citas válidas, tasa de abstención correcta en preguntas sin respuesta. La de recuperación corre en CI; la completa, con LLM, corre en local con la RX 6600.
- [ ] Set de prompt injection (en `tests/security/`): documentos con instrucciones ocultas ("ignorá tus reglas", texto blanco sobre blanco, links a sitios externos). El modelo no debe obedecerlas.
- [ ] Salida segura en el frontend: Markdown sin HTML crudo y sin cargar imágenes ni links externos automáticamente.
- [ ] Experimentos que solo se quedan si mejoran las métricas: reranking con un cross-encoder multilingüe (medir la latencia en CPU), Docling para documentos con tablas, ajuste del tamaño de los fragmentos.
- [ ] Seguridad del código en CI: Bandit, pip-audit y Trivy sobre las imágenes.

## Fuera de alcance

- Fine-tuning de modelos (backlog).
- Prometheus, Grafana y dashboards (etapa 10).
- Dejar un experimento que no mejoró las métricas: se documenta y se descarta.

## Criterios de terminado

- [ ] `docs/evaluation/` tiene un informe con métricas antes y después de cada experimento.
- [ ] Los tests de prompt injection pasan en la versión desplegada.
- [ ] La ADR del modelo final justifica la elección con números.

## Notas

- Dónde va cada cosa: código de métricas en `backend/app/ai/evaluation/`, dataset y scripts en `backend/evaluation/`, informes en `docs/evaluation/`.
- Al cerrar esta etapa termina la Fase C: tag `v0.3.0`.

## Referencias

- Parte 1: §7 (filas IA y Dependencias), §8 (tipos de tests, CI y métricas).
