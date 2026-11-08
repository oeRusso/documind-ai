# Etapa 12 — Entrega de portfolio y demo pública

- **Fase:** D — Producción y portfolio (cierra con el release `v1.0.0`)
- **Duración estimada:** 1 semana
- **Rama:** `development` (PR a `main` al cerrar la etapa)
- **Estado:** pendiente

## Objetivo

Que un reclutador entienda el proyecto en 2 minutos y un entrevistador técnico encuentre profundidad en 20.

## Tareas

- [ ] README con diagrama de arquitectura, GIF de la demo, stack, cómo correrlo en local y enlaces a ADRs y métricas.
- [ ] Organización demo con documentos públicos de ejemplo y cuenta de solo lectura que se resetea cada noche; límites de uso más estrictos para la demo y Turnstile en el acceso.
- [ ] Video de 3 minutos con el recorrido completo.
- [ ] Artículo técnico: arquitectura, decisiones, resultados de la evaluación y qué cambiarías con GPU.
- [ ] Release `v1.0.0` con changelog.

## Fuera de alcance

- Extensiones post v1: integración con Dolibarr, servidor MCP, más formatos (XLSX, imágenes, correos), almacenamiento S3.
- Todo lo del backlog de la Parte 1 (§1): SSO, facturación, búsqueda entre organizaciones, agentes, fine-tuning, app móvil.

## Criterios de terminado

- [ ] Alguien ajeno al proyecto entra a la demo y obtiene una respuesta citada sin ayuda.
- [ ] El README responde: qué es, cómo funciona, cómo se probó y cómo se despliega.

## Notas

- Los diagramas de los planes se perdieron en la exportación (`[embedded content: …]`): rehacerlos en Mermaid para el README si no se hizo antes.
- **Sin Turnstile** (ADR 0005): la demo usa límites de uso más estrictos y el campo trampa del registro.

## Referencias

- Parte 1: §1 (alcance de la v1.0), §2 (arquitectura).
- Parte 2: "Extensiones opcionales después de la v1".
