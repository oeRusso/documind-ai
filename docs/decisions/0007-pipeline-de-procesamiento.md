# 0007 — Pipeline de procesamiento: cola, OCR y fragmentos

- **Estado:** aceptada
- **Fecha:** 2026-11-09
- **Etapa:** 05

## Contexto

Cada documento subido tiene que convertirse en fragmentos con su página y su sección, también los PDF
escaneados. Es trabajo pesado (OCR: segundos por página), así que no puede hacerlo la API. El VPS no tiene
GPU, tiene 8 GB compartidos con otros proyectos y más adelante va a correr un LLM: el procesamiento no
puede acapararlo. Y si el worker se cae a mitad de un documento, este no puede quedar trabado ni duplicado.

## Opciones consideradas

Para la cola:

1. **Celery + Valkey** (lo que dicen los planes): maduro, reintentos y tareas periódicas incluidas.
2. **Una tabla de PostgreSQL como cola** (`SELECT ... FOR UPDATE SKIP LOCKED`): un servicio menos, pero
   reintentos, tiempos límite y tareas periódicas habría que escribirlos a mano.

Para el OCR:

1. **OCRmyPDF + Tesseract** (lo que dicen los planes): endereza y rota páginas. Contra: necesita Ghostscript
   y el programa Tesseract, procesa el PDF entero y suma memoria y paquetes a la imagen.
2. **Tesseract a través de PyMuPDF** (`get_textpage_ocr`): PyMuPDF ya trae el motor de Tesseract; solo
   hacen falta los datos de idioma (`tesseract-ocr-spa`, `tesseract-ocr-eng`). Se aplica página por página,
   solo a las escaneadas. Contra: no endereza páginas torcidas.

Para contar tokens:

1. **El tokenizador del modelo de embeddings**: exacto, pero el modelo se elige en la etapa 6.
2. **Una aproximación (palabras + signos)**: cercana para español y sin dependencias; se reemplaza después.

## Decisión

- **Celery + Valkey.** Un solo worker, de a una tarea (`--concurrency=1`, `prefetch 1`), con `mem_limit 1g`
  y `cpus 1.0`. Tareas confirmadas al terminar (`acks_late`). Celery beat dentro del mismo worker corre la
  purga diaria de archivos borrados.
- **El estado vive en la base** (`processing_jobs`), no en Celery. Cada trabajo se **toma** con un UPDATE
  que solo funciona si está pendiente o si su turno venció. El turno dura 3 minutos y se renueva después
  de cada página. Así:
  - dos workers nunca procesan el mismo trabajo;
  - si el worker muere, el turno vence y el trabajo se vuelve a encolar: lo reentrega Valkey, o lo encola
    la API cuando alguien consulta el estado del documento;
  - los fragmentos se reemplazan en una sola transacción al final: una corrida a medias no deja nada y una
    corrida repetida no duplica.
- La API encola **después** del commit (BackgroundTasks). Si Valkey está caído, el trabajo queda pendiente
  y se encola en la siguiente consulta de estado.
- **OCR con PyMuPDF + datos de Tesseract** (spa+eng, 300 dpi), solo en páginas con menos de 40 caracteres y
  con imágenes. Si la evaluación (etapas 6 y 9) muestra problemas con páginas torcidas, se suma OCRmyPDF.
- **Fragmentos** de hasta ~450 tokens aproximados con 40 de solapamiento, cortados primero por títulos.
  Cada uno guarda sección y páginas. `tsv` (búsqueda de texto en español) lo calcula PostgreSQL.
- Módulos: `extraction` lee y limpia texto; `ingestion` maneja trabajos, fragmentos y el pipeline. Ninguno
  lee tablas de `documents`: lo piden por `DocumentsForIngestion` (su capa de aplicación).

## Consecuencias

- Dos contenedores más: `valkey` (128 MB) y `worker` (hasta 1 GB, imagen con los datos de Tesseract).
- Un PDF escaneado de muchas páginas tarda: varios segundos por página en CPU. El tiempo por página queda
  en los logs (`page_extracted`, `page_ocr`, `document_extracted` con `ms_per_page`).
- `CELERY_BROKER_URL` apunta a `valkey`, que solo existe dentro del compose; corriendo la API fuera de los
  contenedores no hay procesamiento (los documentos quedan pendientes).
- La etapa 6 puede cambiar el contador de tokens por el del modelo de embeddings (`chunk_blocks(counter=...)`).

## Evidencia

- `tests/unit/test_chunking.py` y `test_normalization.py`: reglas de corte, solapamiento, páginas,
  encabezados y pies repetidos.
- `tests/unit/test_readers.py`: documentos de ejemplo en `tests/fixtures` (contrato PDF, PDF escaneado,
  Word con tabla, Markdown, TXT con saltos de página). El de OCR corre en el CI (`REQUIRE_OCR=1`).
- `tests/unit/test_process_version.py` y `tests/integration/test_processing_api.py`: worker que muere a
  mitad de camino, mensaje duplicado, tarea falsificada para otra organización, archivo perdido.
- Prueba manual: con el worker apagado, el documento queda pendiente; al prenderlo se procesa solo. En el
  navegador, el PDF escaneado de ejemplo termina con "El personal deberá usar casco…" en su fragmento.
