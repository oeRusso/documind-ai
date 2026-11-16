# 0006 — Almacenamiento y validación de documentos

- **Estado:** aceptada
- **Fecha:** 2026-11-08
- **Etapa:** 04

## Contexto

Las empresas suben contratos, manuales y políticas: archivos privados que pueden traer sorpresas
(un ejecutable renombrado, un PDF roto, un ZIP que se expande a gigabytes). Hay que decidir dónde se
guardan, cómo se valida qué son y cómo se borran sin romper los backups. Restricciones: costo cero,
todo en el VPS, Cloudflare gratis corta pedidos de más de 100 MB.

## Opciones consideradas

Dónde guardar los bytes:

1. **Disco local (volumen de Docker)** detrás de una interfaz `StorageBackend`: simple y gratis. Contra:
   no escala a varios servidores (no hace falta) y depende del backup del VPS.
2. **Almacenamiento S3 compatible (MinIO, Garage, R2)**: escalable, pero suma un servicio y, en R2,
   un proveedor externo. Queda para después de la v1: la interfaz ya lo permite.
3. **Dentro de PostgreSQL (`bytea`)**: backups en un solo lugar, pero infla la base y cada descarga
   pasa por la conexión de la base.

Cómo saber el tipo real:

1. **libmagic (`python-magic`) + abrir el archivo**: mira los bytes, no el nombre. Para PDF, PyMuPDF
   cuenta páginas y detecta contraseña; para DOCX, `zipfile` revisa la estructura.
2. **Confiar en la extensión o en el `Content-Type` del navegador**: los dos los controla quien sube.

Cómo borrar:

1. **Borrado lógico + purga diferida**: el documento desaparece al instante y los archivos se eliminan
   después de `DOCUMENT_PURGE_DAYS` (30).
2. **Borrado inmediato**: restaurar el backup de ayer dejaría filas apuntando a archivos inexistentes.

## Decisión

- **Disco local** detrás de `StorageBackend` (`app/shared/storage.py`), con claves
  `{organization_id}/{uuid}` validadas por expresión regular: el nombre que manda el usuario nunca es
  una ruta, así que no hay *path traversal*. Archivos con permisos `0600`, solo descargables por la API
  (con permiso, auditado y como `attachment`).
- **Tipo por contenido**: libmagic decide, y la extensión tiene que coincidir. Se rechazan PDF que
  piden contraseña para abrirse (los que solo tienen restricciones de impresión se aceptan), archivos
  rotos, más de `MAX_UPLOAD_PAGES` páginas, ZIP que se expanden más de 300 MB y texto con bytes nulos.
- **Límite de tamaño en dos capas**: un middleware rechaza por `Content-Length` antes de leer el cuerpo
  (413), y la recepción cuenta los bytes reales mientras copia a disco. Next.js reenvía hasta 30 MB
  (`proxyClientMaxBodySize`; por defecto corta en 10 MB sin avisar).
- **Duplicados por SHA-256** dentro de la organización, garantizado por un índice único parcial (también
  con dos subidas simultáneas). El mismo archivo en otra organización no es duplicado: cada una tiene
  su copia y nadie se entera de lo que subió otra.
- **Borrado lógico + purga diferida** con `python -m app.jobs.purge_documents`.
- **`document_purge_queue` no tiene RLS** (excepción explícita, ver ADR 0003): solo guarda claves de
  archivos a borrar. El trabajo de purga la lee y después entra a cada organización para borrar las
  filas de documentos, que sí tienen RLS. El test `test_every_table_with_organization_id_has_forced_rls`
  la lista como excepción con este motivo.
- **PyMuPDF 1.x** (no 2.x): la 2.x arrastra onnxruntime y numpy (cientos de MB) y no hace falta. Se usa
  desde esta etapa para contar páginas y detectar contraseña; la etapa 5 lo usa para extraer texto.

## Consecuencias

- Cambiar a S3 es escribir otra clase que cumpla `StorageBackend`; el módulo `documents` no cambia.
- El volumen `documents` tiene que entrar en el backup del VPS (etapa 3 y 11).
- La purga necesita correr todos los días (cron en el VPS; desde la etapa 5 puede ser Celery beat).
- `libmagic1` va en la imagen de la API (unos 8 MB).
- Un documento borrado puede volver a subirse: el índice de duplicados solo mira versiones vivas.

## Evidencia

- `tests/unit/test_file_inspector.py`: el `.exe` renombrado a `.pdf` se rechaza (criterio 1 de la etapa),
  además de PDF con contraseña, PDF roto, ZIP bomb, extensión equivocada y archivos binarios.
- `tests/integration/test_documents_api.py`: otra organización recibe 404 en ver, descargar, borrar y
  subir versión (criterio 2); el mismo archivo dos veces da 409 con el id del existente (criterio 3);
  la purga borra el archivo solo después del plazo.
- Prueba manual en el navegador: un TXT de 20 MB pasa por el proxy de Next.js después de subir el
  límite; antes llegaba cortado y la API esperaba 30 segundos.
