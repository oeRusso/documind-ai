# 0014 — Demo pública: una cuenta compartida de solo lectura

- **Estado:** aceptada
- **Fecha:** 2026-11-15
- **Etapa:** 12

## Contexto

El portfolio necesita que alguien ajeno entre y pruebe sin registrarse. El servidor es chico (una
respuesta a la vez en CPU) y sin Turnstile (ADR 0005), así que la demo no puede convertirse en una
puerta para subir archivos ni para agotar la CPU.

## Opciones consideradas

1. **Registro libre con una organización de ejemplo por persona**: cada visitante tendría su
   historial privado, pero cualquiera podría subir archivos y crear cuentas sin límite.
2. **Una cuenta compartida de solo lectura** (viewer) con contraseña pública, que se resetea cada
   noche: no sube nada, pero las conversaciones de los visitantes se ven entre ellos.

## Decisión

Opción 2:

- Ids fijos (`app/shared/demo.py`), así toda la app la reconoce sin consultar la base.
- `app.jobs.reset_demo` reconstruye todo con el pipeline normal: organización, dueño oculto (sin
  contraseña conocida), cuenta viewer y 4 leyes públicas. Además borra las conversaciones del día.
  Corre cada noche (Celery beat, 3:30 en Argentina).
- La cuenta demo no puede crear organizaciones (`DemoReadOnlyError`) y el slug `demo-publica` está
  reservado.
- Límites del chat por IP (3 por minuto, 20 por día) y 200 preguntas por día en total.
- El login ofrece «Probar la demo» y la app avisa: cuenta compartida, se borra cada noche, no
  escribas datos personales.
- Se activa con `DEMO_PASSWORD`; vacía, no hay demo.

## Consecuencias

- Los visitantes del mismo día ven las conversaciones de los demás. Está avisado, y el reset diario
  limita la exposición.
- El límite total protege al VPS, pero un día con muchas visitas deja la demo sin respuestas hasta
  el día siguiente (responde 429 con su mensaje).
- Los límites viven en memoria de la API: un reinicio los pone en cero. Con una sola instancia
  alcanza.

## Evidencia

- `tests/integration/test_demo.py`: el reset es idempotente y borra las conversaciones; la cuenta no
  puede crear organizaciones, subir ni ver analíticas; la cuarta pregunta en un minuto da 429.
- Prueba en el entorno local: login con «Probar la demo», los 4 documentos procesados y una
  respuesta correcta con su cita (vacaciones, art. 150) en 25 s.
