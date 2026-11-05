# Etapa 4 — Upload y almacenamiento seguro

- **Fase:** B — Pipeline documental
- **Duración estimada:** 1 semana
- **Rama:** `development` (PR a `main` al cerrar la etapa)
- **Estado:** pendiente

## Objetivo

Guardar documentos de forma privada, validada y aislada por organización.

## Tareas

- [ ] Tablas `documents` y `document_versions` (con `organization_id` y RLS), con hash SHA-256 para detectar duplicados.
- [ ] Upload por streaming (sin cargar el archivo entero en memoria) con límite de tamaño de 25 MB (Cloudflare gratis corta en 100 MB).
- [ ] Validación del tipo real por firma de archivo con python-magic (no por extensión), cantidad de páginas y rechazo de PDFs cifrados o corruptos.
- [ ] Interfaz `StorageBackend` con implementación en filesystem: rutas `/{org_id}/{uuid}`, nombres aleatorios, sin path traversal. La interfaz permite cambiar a almacenamiento S3 compatible sin tocar el módulo `documents`.
- [ ] Descarga solo a través de la API con permisos; nunca una URL pública al archivo.
- [ ] Borrado lógico (`deleted_at`) y borrado físico diferido para respetar los backups.
- [ ] Frontend: lista de documentos, upload con barra de progreso, detalle con metadatos.

## Fuera de alcance

- Extracción de texto, OCR, chunking y workers (etapa 5). El documento queda en estado `pending`.
- Formatos fuera de PDF, DOCX, TXT y Markdown (backlog post v1).
- Almacenamiento S3 (MinIO, Garage): solo se deja la interfaz preparada (extensión post v1).
- Edición de documentos dentro de la app (backlog).

## Criterios de terminado

- [ ] Un `.exe` renombrado a `.pdf` es rechazado.
- [ ] Un usuario de otra organización recibe 404 al pedir el documento (404, no 403, para no revelar que existe).
- [ ] Subir el mismo archivo dos veces crea una versión nueva o avisa del duplicado, no dos documentos sueltos.

## Notas

- La Parte 1 (§7) pide un límite de páginas, pero no hay variable para eso. Sugerencia: `MAX_UPLOAD_PAGES`.
- Variables de entorno que entran: `STORAGE_PATH`, `MAX_UPLOAD_MB`.

## Referencias

- Parte 1: §5 (entidades de la etapa 4), §6 (pasos 1 y 2 del pipeline), §7 (fila Archivos).
