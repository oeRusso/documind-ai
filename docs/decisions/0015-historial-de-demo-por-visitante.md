# 0015 — Historial de la demo por visitante

- **Estado:** aceptada (modifica una consecuencia de [0014](0014-demo-publica.md))
- **Fecha:** 2026-11-16
- **Etapa:** 03 (después del primer despliegue)

## Contexto

La demo pública usa una sola cuenta compartida de solo lectura (ADR 0014), y sus conversaciones se
veían entre todos los visitantes del día. En producción se vio en la práctica: las preguntas de
prueba de una persona aparecían en el historial de la siguiente. Cualquiera podía dejar un texto
ofensivo o un dato personal a la vista del próximo visitante (por ejemplo, alguien que llega desde
el portfolio). El aviso y el reset de cada noche no alcanzan.

## Opciones consideradas

1. **Una cuenta temporal por visitante**: el historial privado sale gratis (ADR 0010), pero hay que
   crear usuarios sin registro, con límites aparte para no llenar la base.
2. **Un identificador por navegador**: una cookie aleatoria `demo_visitor` (`HttpOnly`, `Secure`,
   ruta `/api/v1/conversations`) y una columna `demo_visitor_id` en `conversations`. No crea cuentas
   ni cambia los casos de uso: el repositorio filtra también por esa columna.
3. **Dejarlo como está**: cero trabajo, pero el riesgo sigue.

## Decisión

Opción 2. Solo para la cuenta demo: el repositorio de conversaciones filtra por organización, persona
y `demo_visitor_id IS NOT DISTINCT FROM <cookie>`; para las demás cuentas la columna es NULL y nada cambia.

## Consecuencias

- Cada navegador ve solo sus conversaciones. Otro visitante recibe 404 al pedir, borrar o seguir una
  conversación ajena, como entre organizaciones.
- La cookie no da permisos: solo elige qué historial se ve. Es un UUID v4 (aleatorio; los ids v7 del
  resto de la app llevan la hora y no sirven para esto). Una cookie inventada o inválida empieza un
  historial vacío.
- Borrar las cookies o cambiar de navegador pierde el historial; igual se borra cada noche.
- La migración 0008 solo agrega una columna que admite NULL: el código anterior sigue funcionando y se
  puede volver atrás sin bajar la base.
- La cookie se entrega en los endpoints JSON (listar o empezar una conversación), no en la respuesta
  por SSE; la página siempre llama a uno de ellos antes de preguntar.

## Evidencia

`tests/integration/test_demo.py::test_each_demo_visitor_sees_only_their_own_conversations`: dos
navegadores con la misma cuenta demo; el segundo no lista, no lee, no borra ni pregunta en la
conversación del primero (404), y con una cookie falsa tampoco ve nada.
