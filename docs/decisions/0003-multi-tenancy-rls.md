# 0003 — Organización activa por header y RLS con contexto por transacción

- **Estado:** propuesta
- **Fecha:** 2026-11-06
- **Etapa:** 02

## Contexto

Varias organizaciones comparten la misma base. La Parte 1 (§5) exige aislamiento en dos capas:
el backend filtra por `organization_id` y, si se olvida, PostgreSQL lo frena con Row Level Security (RLS).
Para eso hay que resolver tres cosas:

1. Cómo indica el cliente con qué organización está trabajando (un usuario puede estar en varias).
2. Cómo le dice la app a PostgreSQL quién está consultando, sin abrir una conexión por organización.
3. Qué hacer con las consultas que ocurren **antes** de conocer la organización: el login busca al usuario
   por email, el selector lista las organizaciones del usuario y aceptar una invitación busca el token.

## Opciones consideradas

Para la organización activa:

1. **Header `X-Organization-Id`**: URLs cortas (`/api/v1/documents`, como pide la convención), cambiar de
   organización no requiere otro token y el rol se lee de la base en cada request, así que un cambio de
   rol o una baja tiene efecto inmediato. Contra: el header no se ve en la URL.
2. **En la ruta** (`/api/v1/organizations/{id}/documents`): explícito, pero alarga todas las rutas y
   choca con la convención de recursos de primer nivel.
3. **Dentro del JWT**: no consulta la base para saber la organización, pero cambiar de organización obliga
   a emitir otro token, y un rol revocado sigue vigente hasta que el token vence (15 minutos).

Para el contexto de PostgreSQL:

1. **Variables de sesión por transacción** (`set_config('app.current_org', ..., true)`): el `true` las
   limita a la transacción, así que no se filtran a otra request cuando la conexión vuelve al pool.
2. **Un rol de base por organización**: aislamiento fuerte, pero inmanejable con muchas organizaciones.

## Decisión

- La organización activa viaja en el header `X-Organization-Id`. Una dependencia de FastAPI valida el
  access token, busca la membresía y entrega `CurrentMember(user_id, organization_id, role)` a los casos de uso.
  Si el usuario no es miembro de esa organización, la respuesta es **404**.
- La app fija dos variables por transacción con `set_config(..., true)`: `app.current_user` y `app.current_org`.
  Se usa `set_config` y no `SET LOCAL` porque `SET` no acepta parámetros con asyncpg.
- Las políticas leen las variables con `NULLIF(current_setting('app.current_org', true), '')::uuid`.
  En una conexión reutilizada, una variable ya usada vuelve como `''` (no como `NULL`), y `''::uuid` falla.
- Las políticas usan dos funciones, `current_org_id()` y `current_user_id()`, para que se lean fácil.
- Crear una organización cambia el contexto: el caso de uso llama a `TenantContext.set_organization`
  con el id nuevo antes de insertarla (puerto en `app/shared/tenancy.py`).
- Todas las tablas con RLS usan `ENABLE` y `FORCE ROW LEVEL SECURITY`. La app usa el rol `app`
  (sin `BYPASSRLS` y no dueño de las tablas).

Políticas:

| Tabla | Política | Motivo |
| --- | --- | --- |
| `organizations` | `id = org` o existe una membresía de `user` en ella | El selector muestra los nombres de mis organizaciones. |
| `memberships` | `organization_id = org` o `user_id = user` | El selector lista mis membresías antes de elegir organización. No consulta `organizations`, para evitar recursión entre políticas. |
| `invitations` | `organization_id = org` | El link de invitación lleva la organización además del token: no hace falta saltarse RLS para aceptarla. |
| `audit_logs` | INSERT si `organization_id` es nulo o igual a `org`; SELECT si es igual a `org` | Un login fallido no tiene organización. El rol `app` no tiene `UPDATE` ni `DELETE`: solo inserción. |

`users` y `refresh_tokens` **no** tienen `organization_id` ni RLS. Son tablas de identidad, no de negocio:
un usuario pertenece a varias organizaciones, y el login y el refresh buscan por email o por hash de token
antes de que exista contexto. No guardan datos de ninguna organización. Los repositorios solo exponen
usuarios a través de las membresías de la organización activa.

## Consecuencias

- Una consulta que olvida el `WHERE organization_id` devuelve solo filas de la organización activa
  (lo prueba `tests/security/`).
- Sin contexto fijado, las tablas con RLS devuelven 0 filas: un error de programación falla "cerrado".
- `FORCE` también afecta a `migrator` (dueño de las tablas): una migración que transforme datos vería 0 filas.
  Para eso hay que fijar el contexto o usar el superusuario. `TRUNCATE` no está sujeto a RLS, y por eso
  la limpieza de los tests usa `migrator`.
- El slug duplicado se detecta por la restricción `UNIQUE` (que ve todas las filas), no con un SELECT
  previo (que RLS limitaría a la organización activa).
- Un INSERT con `RETURNING` exige que la fila nueva también pase la política de SELECT. Por eso los
  repositorios mandan `created_at`/`updated_at` desde la app y no piden valores de vuelta a la base
  (en `audit_logs`, un evento sin organización no es legible).
- Los workers de Celery (etapa 5) van a fijar el mismo contexto con el `organization_id` que reciben en la tarea.
- Si `users` llegara a guardar datos sensibles por organización, habría que revisar esta decisión.

## Evidencia

Tests de seguridad de la etapa 2 (`tests/security/test_rls.py` y `tests/security/test_tenant_isolation.py`),
que se agregan en los pasos 4, 5 y 15.
