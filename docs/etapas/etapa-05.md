# Etapa 5 — Workers, extracción, OCR y chunking

- **Fase:** B — Pipeline documental (cierra con el tag `v0.2.0`)
- **Duración estimada:** 1,5 semanas
- **Rama:** `development` (PR a `main` al cerrar la etapa)
- **Estado:** pendiente

## Objetivo

Un pipeline asíncrono confiable que convierte cualquier documento soportado en fragmentos con referencia a página y sección.

## Tareas

- [ ] Valkey y Celery en el compose.
- [ ] Tablas `processing_jobs` (estados: pendiente, extrayendo, OCR, fragmentando, listo, fallido) y `document_chunks` (con `tsv` en español).
- [ ] Tareas idempotentes (reprocesar borra y regenera los fragmentos de esa versión), reintentos con espera creciente, timeout por tarea y mensaje de error guardado cuando falla.
- [ ] El worker recibe `organization_id` y `document_id`, fija el contexto de RLS y vuelve a verificar la pertenencia antes de procesar.
- [ ] Contenedor del worker con límites de memoria y CPU, y como máximo 1 o 2 tareas a la vez para no ahogar al LLM.
- [ ] Extracción con PyMuPDF página por página (python-docx para DOCX).
- [ ] Las páginas con poco texto pasan por OCRmyPDF con Tesseract en español e inglés.
- [ ] Soporte inicial: PDF, DOCX, TXT y Markdown.
- [ ] Normalización: Unicode, guiones de corte de línea, encabezados y pies de página repetidos.
- [ ] Chunking por estructura (títulos y párrafos), de unos 400 a 600 tokens con solapamiento pequeño; cada fragmento guarda página inicial, página final y sección.
- [ ] Frontend: estado del procesamiento en vivo (polling o Server-Sent Events) y vista de los fragmentos de un documento.

## Fuera de alcance

- Embeddings, pgvector y búsqueda (etapa 6).
- Docling y parsing avanzado de tablas (etapa 9, solo si mejora métricas).
- Cualquier formato extra: "nada más hasta que esto sea sólido".

## Criterios de terminado

- [ ] Un PDF escaneado termina con texto legible en sus fragmentos.
- [ ] Matar el worker a mitad de un proceso y reiniciarlo no deja el documento trabado ni duplicado.
- [ ] Hay tests de chunking con documentos de ejemplo guardados en `tests/fixtures`.
- [ ] Registrás el tiempo de procesamiento por página en los logs.

## Notas

- **Estados del pipeline**: la Parte 1 (§6) incluye `embedding` entre `chunking` y `ready`. En esta etapa todavía no hay embeddings, así que el flujo termina en `chunking` → `ready`. El estado `embedding` se agrega en la etapa 6.
- **Chunking**: es una de las piezas clave para escribir vos (riesgo "código generado que no entendés"). Tests primero.
- `CELERY_BROKER_URL` usa el esquema `redis://` contra Valkey: es correcto, el protocolo es compatible. Probablemente haga falta también `CELERY_RESULT_BACKEND`.
- Al cerrar esta etapa termina la Fase B: tag `v0.2.0`.

## Referencias

- Parte 1: §5 (entidades de la etapa 5), §6 (pipeline de ingesta), §7 (fila Procesamiento).
