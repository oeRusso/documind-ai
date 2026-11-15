# Documentos de la demo pública

Leyes argentinas en PDF, generadas desde el texto público de Infoleg (InfoLEG, Ministerio de
Justicia de la Nación) por `backend/evaluation/build_corpus.py`. Origen, fecha y SHA-256 en
`backend/evaluation/corpus/manifest.json`. Las leyes son de dominio público (art. 1 de la
ley 11.723 no las protege como obra: son actos de gobierno).

`app/jobs/reset_demo.py` las carga en la organización demo cada noche, si faltan.
