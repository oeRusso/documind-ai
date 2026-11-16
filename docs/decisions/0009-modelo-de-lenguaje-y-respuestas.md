# 0009 — Respuestas con citas: modelo de lenguaje, umbral y memoria

- **Estado:** aceptada
- **Fecha:** 2026-11-12
- **Etapa:** 07

## Contexto

La etapa 7 responde preguntas con los fragmentos que encuentra la búsqueda (ADR 0008), citándolos.
Hay que decidir tres cosas: qué modelo de lenguaje escribe las respuestas, a partir de qué similitud se
responde «no encontré evidencia» sin llamar al modelo (`RAG_MIN_SCORE`) y cuánta memoria hay que darle a
Ollama. Las restricciones son las mismas que en la ADR 0008: todo corre local con Ollama, en CPU y sin
GPU, en un VPS con 8 GB compartidos con otros proyectos. Además, la licencia del modelo tiene que
permitir este uso, y la descarga tiene que ser gratuita.

## Opciones consideradas

Modelos de 1 a 3 mil millones de parámetros, cuantizados (Q4), del registro gratuito de Ollama:

1. **granite3.3:2b** (IBM, Apache 2.0, 1,5 GB): el más liviano y con la licencia más simple.
2. **llama3.2:3b** (Meta, Llama 3.2 Community License, 2,0 GB): uso comercial gratuito, con la condición
   de mostrar «Built with Llama».
3. Se descartaron **Qwen 2.5 3B**, porque su licencia es solo para investigación, y los modelos de 7B o
   más, porque no entran en la RAM del VPS.

Para el umbral se probaron valores entre 0,40 y 0,65 de similitud por significado (bge-m3) del fragmento
más cercano. El puntaje de la búsqueda híbrida (RRF) no sirve como umbral: ordena los resultados, pero
no dice qué tan cerca está cada uno de la pregunta.

## Decisión

- **`LLM_MODEL=llama3.2:3b`.**
- **`RAG_MIN_SCORE=0.5`.**
- **Ollama con la caché de prompts de llama.cpp apagada (`LLAMA_ARG_CACHE_RAM=0`) y `mem_limit` de 4,5 GB.**
- Una respuesta a la vez (`LLM_MAX_CONCURRENCY=1`). Las demás preguntas esperan en una cola en memoria
  y ven su posición.

## Consecuencias

- **Por qué llama3.2:3b.** En la muestra de 24 preguntas con respuesta citó la página correcta en 15, contra
  9 de granite, y solo 2 de sus respuestas salieron sin ninguna cita (11 en granite). Además, dijo «no encontré» en las 11 preguntas sin respuesta y terminó antes, porque sus
  respuestas son más cortas. El costo es unos 0,6 GB más de RAM que granite.
- **Licencia.** El README muestra «Built with Llama», como pide la licencia de Llama 3.2.
- **Umbral 0,50.** Frena 6 de las 11 preguntas sin respuesta antes de llamar al modelo, sin frenar
  ninguna de las 68 que sí tienen respuesta. Las otras 5 sin respuesta llegan al modelo, y el modelo
  también contestó «no encontré» en todas. Con 0,52 se frenarían 8, pero ya se perdería una con
  respuesta. El dataset es chico (79 preguntas): conviene volver a calibrar cuando crezca.
- **Memoria.** La caché de prompts de llama.cpp guarda en RAM cada prompt anterior, hasta 8 GB por
  defecto, unos 177 MB por pregunta en nuestro caso. Con un límite de 4 GB, el sistema mató el proceso
  del modelo a mitad de la evaluación (`oom_kill` en el cgroup). Cada pregunta trae fragmentos distintos,
  así que esa caché casi no ayuda: se apagó. Con la caché apagada, Ollama usa **3,92 a 3,95 GB fijos**
  (bge-m3 1,28 GB + llama3.2:3b 2,59 GB), también con 5 preguntas a la vez. Con granite serían 3,30 GB.
  El pico de 4,46 GB que el informe muestra para granite es del momento del cambio de modelo, cuando el
  llama que había cargado la API todavía estaba en memoria. `OLLAMA_MAX_LOADED_MODELS` no lo evitó, y en
  producción no pasa porque se usa un solo LLM.
- **VPS (etapa 3).** Ollama solo necesita unos 4 GB de los 8 GB compartidos. Entra, pero hay que medir
  `free -h` antes de desplegar. Si falta memoria, la salida es `LLM_MODEL=granite3.3:2b` (unos 0,6 GB
  menos) a cambio de citas peores, o el modelo de embeddings liviano (ADR 0008), a cambio de peor
  búsqueda.
- **Velocidad.** En la PC de desarrollo (16 núcleos), una respuesta de llama tarda unos 19 s (p50; p95 de
  25 s), y el primer texto aparece a los 15 s, porque leer el contexto (unos 1.500 tokens) es lo que más cuesta en CPU. En
  el VPS va a ser más lento, por eso se ve la posición en la cola y se puede detener la respuesta.
- **Prompt.** Con solo reglas, granite citaba a su manera (`[1, Art. 92 bis]`, «fragmento n°1») y el
  filtro descartaba esas citas. Agregar un ejemplo de respuesta bien citada al prompt lo corrigió.
- **Compresión y streaming.** Next.js comprimía con gzip lo que reenvía, y eso retenía el stream hasta
  el final. Se apagó la compresión de Next (`compress: false`). Caddy tiene que hacer lo mismo con
  `text/event-stream` (nota en la etapa 3).
- **Dónde vive.** La generación de respuestas quedó en el módulo `knowledge`, junto a la búsqueda,
  porque en esta etapa no hay tablas de conversaciones. En la etapa 8, `conversations` guarda mensajes y
  citas, y llama a `knowledge` por su capa `application`.

## Evidencia

- `docs/evaluation/answers-2026-11-12.md` y `backend/evaluation/results/answers.json` (con cada respuesta),
  generados por `uv run python -m evaluation.eval_answers`.
- Prueba de carga: `uv run python -m evaluation.load_chat`. Las 5 preguntas simultáneas recibieron
  respuesta en 81 s en total, en orden de cola (posiciones 3, 2, 1). La pregunta fuera de tema se
  respondió en 1,5 s sin usar el modelo. Pico de RAM: Ollama 3,95 GB, API 0,12 GB.
- Medición de memoria: `podman exec documind-ollama-1 cat /sys/fs/cgroup/memory.stat` (`anon`).
  `podman stats` no sirve para esto: suma caché de archivos que el kernel libera solo y muestra el
  límite, no el uso real.
