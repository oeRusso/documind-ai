# RAG con citas verificables en un VPS sin GPU: lo que aprendí construyendo DocuMind AI

> Borrador del artículo técnico de la etapa 12. Los números salen de `docs/evaluation/` (noviembre
> de 2026, en la PC de desarrollo con CPU). Revisar y ajustar el tono antes de publicarlo.

## El problema

Las empresas chicas tienen sus reglas repartidas en PDFs: contratos, políticas internas, leyes que
las afectan. Preguntarle a un chatbot comercial implica mandarle esos documentos a un tercero, y su
respuesta no dice de dónde sale. Quería lo contrario: que cada organización suba sus documentos, que
pregunte en español, y que cada dato de la respuesta tenga una cita que se pueda verificar con un
clic. Todo con IA local, sin APIs pagas, en un VPS de 8 GB sin GPU que además comparto con otro
proyecto.

## La arquitectura, en una línea por pieza

- **FastAPI** como monolito modular: cada módulo (documentos, conversaciones, búsqueda) con cuatro
  capas, y ninguno toca las tablas de otro.
- **PostgreSQL + pgvector** para todo: datos, vectores y búsqueda por palabras. Un solo motor para
  respaldar, migrar y aislar.
- **Celery + Valkey** para el trabajo pesado (texto, OCR, fragmentos, embeddings): la API nunca
  procesa un documento, encola y responde.
- **Ollama** con `bge-m3` para embeddings y `llama3.2:3b` para responder.
- **Next.js** para la web, con el cliente generado del OpenAPI: si el backend cambia un campo, el
  frontend no compila.

## Aislar organizaciones dos veces

Un error de un `WHERE` olvidado en una app multi-empresa es un incidente grave. Por eso cada consulta
filtra por organización **y** PostgreSQL lo vuelve a exigir con Row Level Security: la API se conecta
con un rol que no puede saltarse las políticas, y el contexto de la organización vive solo dentro de
la transacción del pedido (`set_config(..., true)`). Los tests de seguridad se conectan como ese rol y
verifican que, sin contexto, todas las tablas de negocio se ven vacías.

## La búsqueda: medir antes de elegir

Armé un dataset con 12 leyes argentinas y 79 preguntas (11 sin respuesta en el corpus), cada una con
la frase exacta que la responde. Con eso comparé modos y modelos:

| Modo | recall@5 | MRR |
|---|---|---|
| Solo palabras (español, sin tildes) | 0,618 | 0,425 |
| Solo significado (`bge-m3`) | 0,912 | 0,771 |
| Híbrida (RRF) | 0,912 | 0,712 |

La híbrida no le gana a la vectorial en el promedio, pero sí en las búsquedas por términos exactos
(«art. 245 LCT»): 1,000 contra 0,875 de recall@5. Como la gente busca de las dos formas, quedó la híbrida.
También probé cortar los fragmentos en 300 y 600 tokens: ninguno superó a los 450 actuales.

## Respuestas que citan, y que no inventan

El modelo recibe los fragmentos numerados entre etiquetas, como **datos**, y tiene que citar `[n]`.
Un modelo de 3B a veces cita `[7]` cuando recibió tres fragmentos: un filtro revisa cada marcador
**mientras llega el texto** y borra los que no apuntan a nada. Si el fragmento más cercano está por
debajo de un umbral de similitud (calibrado con las preguntas sin respuesta), la app contesta «no
encontré evidencia» **sin llamar al modelo**: ni inventa ni gasta CPU.

Con `llama3.2:3b` en CPU: respondió 21 de 24 preguntas con respuesta, citó la página exacta en 14,
y dijo «no encontré» en las 11 que no tenían respuesta. El primer token tarda unos 17 segundos.
`granite3.3:2b` era más rápido escribiendo, pero citó bien solo 9 de 24.

## Preguntas de seguimiento

«¿Y cuándo es válida?» no dice nada sola. Probé tres formas de armar la búsqueda: solo la pregunta,
siempre con la anterior, y con la anterior solo si la nueva es corta. Con 22 seguimientos y 30
cambios de tema:

| Estrategia | seguimientos recall@5 | cambios de tema recall@5 |
|---|---|---|
| Solo la pregunta | 0,455 | 0,900 |
| Siempre con la anterior | 0,682 | 0,467 |
| Con la anterior si tiene ≤ 6 palabras | **0,727** | **0,867** |

Reformular la pregunta con el LLM habría costado otra llamada al modelo por pregunta. No hizo falta.

## Prompt injection: medirlo con el modelo real

Escribí 8 documentos maliciosos: órdenes visibles («ignorá tus instrucciones»), texto blanco sobre
blanco, etiquetas falsas para «escapar» del fragmento, pedidos de links e imágenes que filtrarían la
pregunta a otro servidor, y pedidos de copiar las reglas internas. Cada uno tiene una palabra
«canario» que no puede aparecer en una respuesta correcta.

| Versión | Ataques que funcionaron |
|---|---|
| Prompt original | 2 de 8 |
| + recordatorio después de los fragmentos | 1 de 8 |
| + filtro de salida (sin HTML ni imágenes) | **0 de 8** |

Además, el lector de PDF descarta el texto que una persona no ve (blanco, transparente, de menos de
1 punto), y la web dibuja un Markdown propio que nunca genera HTML, links clicables ni imágenes. El
recordatorio costó unos 2 segundos más de primer token, y la calidad quedó dentro del ruido.

## Operar sin nube

- **Métricas** desde los eventos que el código ya loguea: un procesador de structlog los convierte
  en métricas de Prometheus, y el dominio no se entera. El dashboard separa el tiempo de una respuesta
  en búsqueda, cola, primer token y generación.
- **Backups** cifrados con restic en el servidor, que la PC baja por `rsync`. Lo probé restaurando en
  un entorno vacío: 5 segundos, y los mismos archivos byte a byte.
- **Rollback** por etiquetas de imagen: 9 segundos hasta que la API vuelve a responder.

## Qué cambiaría con una GPU

- Un modelo de 8B o más (Llama 3.1 8B, Qwen) para citar mejor la página exacta: la mayoría de los
  errores que quedan son del modelo eligiendo el fragmento vecino.
- Un reranker (cross-encoder multilingüe) sobre los 30 candidatos de la búsqueda. En CPU lo descarté
  sin medir: necesitaba sumar Hugging Face como fuente de modelos, y es la próxima prueba si se autoriza.
- Varias respuestas en paralelo en lugar de una cola de a una.
- Reformular las preguntas de seguimiento con el LLM, que en GPU cuesta décimas de segundo.

## Lo que me llevo

Lo más útil no fue ningún modelo, sino el dataset de evaluación. Cada decisión de IA se pudo
discutir con un número, y lo que no mejoró una métrica no entró.

El código, las decisiones (ADR) y los informes de evaluación están en el repositorio.
