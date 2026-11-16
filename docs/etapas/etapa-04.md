# Etapa 4 — Upload y almacenamiento seguro

- **Fase:** B — Pipeline documental
- **Duración estimada:** 1 semana
- **Rama:** `development` (PR a `main` al cerrar la etapa)
- **Estado:** terminada (2026-11-08), en `development` (sin PR por etapa: ver `CLAUDE.md`, "Git").

## Objetivo

Guardar documentos de forma privada, validada y aislada por organización.

## Tareas

- [x] Tablas `documents` y `document_versions` (con `organization_id` y RLS), con hash SHA-256 para detectar duplicados.
- [x] Upload por streaming (sin cargar el archivo entero en memoria) con límite de tamaño de 25 MB (Cloudflare gratis corta en 100 MB).
- [x] Validación del tipo real por firma de archivo con python-magic (no por extensión), cantidad de páginas y rechazo de PDFs cifrados o corruptos.
- [x] Interfaz `StorageBackend` con implementación en filesystem: rutas `/{org_id}/{uuid}`, nombres aleatorios, sin path traversal. La interfaz permite cambiar a almacenamiento S3 compatible sin tocar el módulo `documents`.
- [x] Descarga solo a través de la API con permisos; nunca una URL pública al archivo.
- [x] Borrado lógico (`deleted_at`) y borrado físico diferido para respetar los backups.
- [x] Frontend: lista de documentos, upload con barra de progreso, detalle con metadatos.

## Fuera de alcance

- Extracción de texto, OCR, chunking y workers (etapa 5). El documento queda en estado `pending`.
- Formatos fuera de PDF, DOCX, TXT y Markdown (backlog post v1).
- Almacenamiento S3 (MinIO, Garage): solo se deja la interfaz preparada (extensión post v1).
- Edición de documentos dentro de la app (backlog).

## Criterios de terminado

- [x] Un `.exe` renombrado a `.pdf` es rechazado.
- [x] Un usuario de otra organización recibe 404 al pedir el documento (404, no 403, para no revelar que existe).
- [x] Subir el mismo archivo dos veces crea una versión nueva o avisa del duplicado, no dos documentos sueltos.

## Notas

- La Parte 1 (§7) pide un límite de páginas, pero no hay variable para eso. Sugerencia: `MAX_UPLOAD_PAGES`.
- Variables de entorno que entran: `STORAGE_PATH`, `MAX_UPLOAD_MB`.

## Resultado

**Criterios de terminado: los tres cumplidos.**

1. Un `.exe` renombrado a `.pdf` se rechaza (415 `unsupported_file_type`): `tests/unit/test_file_inspector.py`
   y `tests/integration/test_documents_api.py`, y en el navegador.
2. Otra organización recibe 404 al ver, descargar, borrar o subir una versión: `test_documents_api.py`
   y `tests/security/` (RLS en `documents` y `document_versions`).
3. El mismo archivo dos veces da 409 `duplicate_document` con el id del existente; la UI muestra
   "Ver el documento". Una versión nueva se sube desde el detalle.

**Qué quedó:**

- Backend: módulo `documents` (4 capas), migración `0004`, `StorageBackend` en disco, inspector de
  archivos (libmagic + PyMuPDF + zipfile), purga diferida (`python -m app.jobs.purge_documents`).
- Frontend: `/documents` (subida múltiple arrastrando, barra de progreso, lista paginada) y
  `/documents/[id]` (versiones, descarga, versión nueva, borrar). Es la página de inicio.
- Permisos: lector ve y descarga; miembro sube y borra lo suyo; admin y owner borran cualquiera.
- **Números:** 386 tests de backend y 29 de frontend. Recorrido en Chrome headless: PDF y TXT de 20 MB
  subidos, `.exe` rechazado, duplicado avisado, descarga, borrado, lector sin zona de subida.

**Decisiones:** ADR 0006 (almacenamiento y validación). `MAX_UPLOAD_PAGES` (500) quedó como variable.

**Problema encontrado:** Next.js reenvía solo 10 MB del cuerpo en los `rewrites` y corta el resto sin
error; la API esperaba el resto 30 s. Se subió a 30 MB (`proxyClientMaxBodySize` en `next.config.ts`).

**Pendientes para etapas siguientes:**

- Etapa 5: el estado queda en `pending`; el pipeline lo mueve. La purga puede pasar a Celery beat.
- Etapa 3/11: el volumen `documents` tiene que entrar en el backup y la purga en un cron del VPS.

## Referencias

- Parte 1: §5 (entidades de la etapa 4), §6 (pasos 1 y 2 del pipeline), §7 (fila Archivos).
