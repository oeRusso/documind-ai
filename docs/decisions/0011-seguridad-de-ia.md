# 0011 — Seguridad de IA: defensas contra prompt injection y experimentos de la etapa 9

- **Estado:** aceptada
- **Fecha:** 2026-11-15
- **Etapa:** 09

## Contexto

El contenido de los documentos es dato, no instrucción (`CLAUDE.md`). Desde la etapa 7 el prompt marca
los fragmentos entre etiquetas y desactiva etiquetas falsas, pero nunca se había medido si el modelo
(`llama3.2:3b`, ADR 0009) obedece órdenes escritas en un documento. La etapa también pide experimentos
que solo se quedan si mejoran las métricas.

## Opciones consideradas

1. **Confiar en el prompt de la etapa 7**: 2 de 8 ataques ganaron (copiar las reglas internas,
   cambiar de rol y firmar).
2. **Recordatorio después de los datos** ("sándwich"): repetir la regla justo antes de la pregunta,
   que es lo último que lee el modelo. Gratis, pero cambia el prompt.
3. **Filtro de salida** (`OutputGuard`): sacar del stream HTML e imágenes Markdown, que una
   respuesta nunca necesita. No depende del modelo.
4. **Clasificador de inyección con otro modelo**: una llamada más por pregunta (10–20 s en CPU).
5. **Quitar el texto invisible de los PDF** (blanco, transparente, < 1 pt) al extraer.

## Decisión

Capas 2, 3 y 5, más dos capas en la web: Markdown propio que nunca dibuja HTML, links ni imágenes,
y una Content Security Policy que no deja cargar imágenes ni conectar con otros sitios. La 4 no:
cuesta demasiado en CPU y las otras ya llegan a 8 de 8.

Experimentos:
- **Tamaño de fragmentos** (300 / 450 / 600 tokens): ninguno supera a 450. Se descarta.
- **Reranking con cross-encoder** y **Docling**: no se corrieron. Ollama no tiene reranking, y los dos
  necesitan bajar modelos de Hugging Face (y PyTorch): una fuente externa nueva que `CLAUDE.md` pide
  autorizar antes. Además el corpus no tiene tablas, así que Docling no tendría qué mejorar.
  **Esteban no autorizó Hugging Face (2026-11-15): los dos quedan descartados.**

## Consecuencias

- El primer token tarda unos 2 s más (16,8 s contra 14,7 s de p50): el prompt es más largo.
- Las citas a la página correcta pasan de 15/24 a 14/24 (perdió 2 y ganó 1: nivel de ruido con 24
  preguntas). La abstención sigue en 11/11.
- El texto blanco sobre fondo oscuro también se descarta: es raro, y perderlo es más seguro que dárselo
  al modelo. Se loguea (`hidden_text_dropped`).
- Los links quedan como texto en las respuestas (un documento puede tener una dirección legítima); la
  web no los hace clicables.
- `evaluation.eval_injection` corre por HTTP: el mismo set se prueba contra la versión desplegada.

## Evidencia

- [injection-2026-11-15.md](../evaluation/injection-2026-11-15.md) (versión final). Secuencia medida:
  sin cambios 2/8 ataques ganaron → con el recordatorio 1/8 (copiar HTML) → con el filtro de salida 0/8.
- [answers-2026-11-15.md](../evaluation/answers-2026-11-15.md) contra [answers-2026-11-12.md](../evaluation/answers-2026-11-12.md).
- Fragmentos: [300](../evaluation/retrieval-2026-11-15-chunks300.md), [450](../evaluation/retrieval-2026-11-11.md),
  [600](../evaluation/retrieval-2026-11-15-chunks600.md). Híbrida bge-m3: recall@5 0,912 / 0,912 / 0,897;
  MRR 0,678 / 0,712 / 0,709.
- Seguridad del código: Bandit sin hallazgos medios ni altos; pip-audit sin vulnerabilidades; Trivy
  encontró zlib (Debian) en el backend y `undici`/`brace-expansion` del npm de la imagen web; se
  corrigió con `apt-get upgrade` y quitando npm: 0 altas o críticas con parche en las tres imágenes.
