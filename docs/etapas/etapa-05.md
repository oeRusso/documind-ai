# Etapa 5 — Workers, extracción, OCR y chunking

- **Fase:** B — Pipeline documental (cierra con el tag `v0.2.0`)
- **Duración estimada:** 1,5 semanas
- **Rama:** `development` (PR a `main` al cerrar la etapa)
- **Estado:** terminada (2026-11-09), en `development`. Cierra la Fase B (tag `v0.2.0` al pasar a `main`).

## Objetivo

Un pipeline asíncrono confiable que convierte cualquier documento soportado en fragmentos con referencia a página y sección.

## Tareas

- [x] Valkey y Celery en el compose.
- [x] Tablas `processing_jobs` (estados: pendiente, extrayendo, OCR, fragmentando, listo, fallido) y `document_chunks` (con `tsv` en español).
- [x] Tareas idempotentes (reprocesar borra y regenera los fragmentos de esa versión), reintentos con espera creciente, timeout por tarea y mensaje de error guardado cuando falla.
- [x] El worker recibe `organization_id` y `document_id`, fija el contexto de RLS y vuelve a verificar la pertenencia antes de procesar.
- [x] Contenedor del worker con límites de memoria y CPU, y como máximo 1 o 2 tareas a la vez para no ahogar al LLM.
- [x] Extracción con PyMuPDF página por página (python-docx para DOCX).
- [x] Las páginas con poco texto pasan por OCRmyPDF con Tesseract en español e inglés.
- [x] Soporte inicial: PDF, DOCX, TXT y Markdown.
- [x] Normalización: Unicode, guiones de corte de línea, encabezados y pies de página repetidos.
- [x] Chunking por estructura (títulos y párrafos), de unos 400 a 600 tokens con solapamiento pequeño; cada fragmento guarda página inicial, página final y sección.
- [x] Frontend: estado del procesamiento en vivo (polling o Server-Sent Events) y vista de los fragmentos de un documento.

## Fuera de alcance

- Embeddings, pgvector y búsqueda (etapa 6).
- Docling y parsing avanzado de tablas (etapa 9, solo si mejora métricas).
- Cualquier formato extra: "nada más hasta que esto sea sólido".

## Criterios de terminado

- [x] Un PDF escaneado termina con texto legible en sus fragmentos.
- [x] Matar el worker a mitad de un proceso y reiniciarlo no deja el documento trabado ni duplicado.
- [x] Hay tests de chunking con documentos de ejemplo guardados en `tests/fixtures`.
- [x] Registrás el tiempo de procesamiento por página en los logs.

## Notas

- **Estados del pipeline**: la Parte 1 (§6) incluye `embedding` entre `chunking` y `ready`. En esta etapa todavía no hay embeddings, así que el flujo termina en `chunking` → `ready`. El estado `embedding` se agrega en la etapa 6.
- **Chunking**: es una de las piezas clave para escribir vos (riesgo "código generado que no entendés"). Tests primero.
- `CELERY_BROKER_URL` usa el esquema `redis://` contra Valkey: es correcto, el protocolo es compatible. Probablemente haga falta también `CELERY_RESULT_BACKEND`.
- Al cerrar esta etapa termina la Fase B: tag `v0.2.0`.

## Resultado

**Criterios de terminado: los cuatro cumplidos.**

1. Un PDF escaneado termina con texto legible: `tests/unit/test_readers.py` (corre en el CI con los datos
   de Tesseract) y en el navegador ("El personal deberá usar casco…").
2. Matar el worker no deja el documento trabado ni duplicado: `test_process_version.py` y
   `test_processing_api.py` (turno vencido, re-encolado, mensaje duplicado), y a mano con el worker apagado.
3. Tests de chunking con documentos de ejemplo en `tests/fixtures` (generados por `make_fixtures.py`).
4. Tiempo por página en los logs del worker: `page_extracted`, `page_ocr` y `document_extracted` (`ms_per_page`).

**Qué quedó:** módulos `extraction` e `ingestion`, migración `0005` (`processing_jobs`, `document_chunks`
con `tsv` en español), contenedores `valkey` y `worker`, rutas `/documents/{id}/processing`, `/reprocess`
y `/chunks`; en la web, panel de procesamiento en vivo y lista de fragmentos. 453 tests de backend y 31 de
frontend.

**Decisiones:** ADR 0007 (Celery + Valkey, turnos con vencimiento, OCR vía PyMuPDF en vez de OCRmyPDF,
tokens aproximados).

**Problemas encontrados:**

- El worker fallaba con `NoReferencedTableError`: su proceso no importaba los modelos de las otras tablas.
  Corregido en `app/worker.py` con un test que arranca el worker en un intérprete limpio.
- Un archivo guardado que falta era tratado como error temporal (reintentos inútiles): ahora es falla
  definitiva con mensaje.

**Pendientes:**

- Valkey y el worker en producción (etapa 3, al final): sumar `mem_limit` y el volumen de Valkey al backup.
- La etapa 6 puede cambiar el contador de tokens por el del modelo de embeddings y agregar el estado
  `embedding` entre `chunking` y `ready`.

## Referencias

- Parte 1: §5 (entidades de la etapa 5), §6 (pipeline de ingesta), §7 (fila Procesamiento).
