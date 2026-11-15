# Etapa 12 — Entrega de portfolio y demo pública

- **Fase:** D — Producción y portfolio (cierra con el release `v1.0.0`)
- **Duración estimada:** 1 semana
- **Rama:** `development` (PR a `main` al cerrar la etapa)
- **Estado:** terminada en local (2026-11-15), en `development`; falta lo que necesita a Esteban o al VPS

## Objetivo

Que un reclutador entienda el proyecto en 2 minutos y un entrevistador técnico encuentre profundidad en 20.

## Tareas

- [x] README con diagrama de arquitectura, GIF de la demo (**pendiente: grabarlo**), stack, cómo correrlo en local y enlaces a ADRs y métricas.
- [x] Organización demo con documentos públicos de ejemplo y cuenta de solo lectura que se resetea cada noche; límites de uso más estrictos para la demo ~~y Turnstile en el acceso~~ (sin Turnstile, ADR 0005 y 0014).
- [ ] Video de 3 minutos con el recorrido completo. **Lo graba Esteban.**
- [x] Artículo técnico (borrador en `docs/articulo-tecnico.md`): arquitectura, decisiones, resultados de la evaluación y qué cambiarías con GPU.
- [ ] Release `v1.0.0` con changelog. **`CHANGELOG.md` listo; el tag va sobre `main` con el PR final.**

## Fuera de alcance

- Extensiones post v1: integración con Dolibarr, servidor MCP, más formatos (XLSX, imágenes, correos), almacenamiento S3.
- Todo lo del backlog de la Parte 1 (§1): SSO, facturación, búsqueda entre organizaciones, agentes, fine-tuning, app móvil.

## Criterios de terminado

- [ ] Alguien ajeno al proyecto entra a la demo y obtiene una respuesta citada sin ayuda. **En local funciona con el botón «Probar la demo»; la prueba con alguien ajeno va en el despliegue.**
- [x] El README responde: qué es, cómo funciona, cómo se probó y cómo se despliega.

## Notas

- Los diagramas de los planes se perdieron en la exportación (`[embedded content: …]`): rehacerlos en Mermaid para el README si no se hizo antes.
- **Sin Turnstile** (ADR 0005): la demo usa límites de uso más estrictos y el campo trampa del registro.

## Resultado

**Criterios:** el README responde qué es, cómo funciona, cómo se probó y cómo se despliega. La demo
funciona en local con el botón «Probar la demo»; la prueba con una persona ajena va después del
despliegue.

**Qué quedó:**

- **Demo** (ADR 0014): `app/shared/demo.py`, `app/jobs/reset_demo.py` (también tarea nocturna de
  Celery), `GET /api/v1/demo`, `app/demo_documents/` (4 leyes públicas), límites por IP y el botón
  y el aviso en la web (`components/demo.tsx`). Se activa con `DEMO_PASSWORD`.
- **README** nuevo con diagrama Mermaid, resultados, cómo correrlo y desplegarlo, y tabla de ADRs.
- `CHANGELOG.md` por fase y borrador de `docs/articulo-tecnico.md`.

**Pendientes (Esteban):**

- Grabar el GIF (`docs/demo.gif`) y el video de 3 minutos.
- Revisar y publicar el artículo.
- PR `development` → `main`, tags `v0.1.0`…`v1.0.0` y despliegue (etapas 0 y 3).

## Referencias

- Parte 1: §1 (alcance de la v1.0), §2 (arquitectura).
- Parte 2: "Extensiones opcionales después de la v1".
