# 0004 — Sesiones: access token en memoria y refresh token rotativo en cookie

- **Estado:** aceptada
- **Fecha:** 2026-11-06
- **Etapa:** 02

## Contexto

La Parte 1 (§7) fija un access token de 15 minutos y un refresh token rotativo, revocable y guardado en
una cookie `HttpOnly; Secure; SameSite`, con protección CSRF y detección de reuso. No define dónde vive el
access token en el frontend ni qué forma tiene cada token.

Hay dos riesgos que se equilibran:

- **XSS** (código JavaScript inyectado en la página): puede leer lo que esté en `localStorage` o en cookies
  sin `HttpOnly`.
- **CSRF** (otro sitio dispara una request usando las cookies del usuario): afecta a todo lo que se
  autentique con cookies.

## Opciones consideradas

1. **Access token en memoria (variable de JavaScript) y refresh token en cookie `HttpOnly`**: un XSS no puede
   robar el refresh token, y las requests normales no usan cookies, así que no son vulnerables a CSRF.
   Contra: al recargar la página hay que pedir un access token nuevo, y no hay datos autenticados renderizados
   en el servidor de Next.js.
2. **Access token en `localStorage`**: sobrevive a la recarga, pero cualquier XSS lo roba.
3. **Los dos tokens en cookies `HttpOnly`**: nada legible por JavaScript, pero **todas** las requests pasan a
   depender de cookies y todas necesitan protección CSRF.

## Decisión

Opción 1.

- **Access token**: JWT HS256 firmado con `JWT_SECRET` (librería PyJWT), válido `ACCESS_TOKEN_MINUTES` (15).
  Lleva solo `sub` (usuario), `type`, `iat`, `exp` y `jti`: ni organización ni rol, que se leen de la base
  en cada request (ADR 0003). Se envía en `Authorization: Bearer`. El frontend lo guarda solo en memoria.
- **Refresh token**: valor aleatorio de 256 bits (`secrets.token_urlsafe`), no un JWT. En la base se guarda
  solo su hash SHA-256, con `family_id` (una familia por login). Vive en una cookie
  `HttpOnly; Secure; SameSite=Lax; Path=/api/v1/auth`, válida `REFRESH_TOKEN_DAYS` (14).
- **Rotación**: cada `POST /auth/refresh` marca el token usado como rotado y entrega uno nuevo de la misma
  familia. La fila se lee con `SELECT ... FOR UPDATE` para que dos refresh simultáneos no se pisen.
- **Reuso**: presentar un token ya rotado revoca toda la familia, cierra esa sesión y queda en `audit_logs`.
- **CSRF**: solo `POST /auth/refresh` y `POST /auth/logout` usan la cookie. Ahí se exige:
  1. que el header `Origin` coincida con `APP_ORIGIN`, y
  2. doble envío: el login deja una cookie `csrf_token` legible por JavaScript, y el frontend la repite en el
     header `X-CSRF-Token`. Se comparan con `hmac.compare_digest`.
- **Mismo origen en desarrollo**: Next.js reenvía `/api/*` al backend (rewrites), igual que va a hacer Caddy
  en producción (etapa 3). No hace falta CORS. Los navegadores aceptan cookies `Secure` en `http://localhost`.

## Consecuencias

- Al recargar, el frontend llama a `/auth/refresh` antes de mostrar páginas privadas. Las páginas privadas son
  componentes de cliente con TanStack Query.
- Si dos pestañas refrescan a la vez con el mismo token, una puede parecer un reuso y cerrar la sesión.
  Lo atenúan el `FOR UPDATE` y que el frontend comparta un solo refresh en curso por pestaña. Si molesta en
  la práctica, se puede sumar un margen de gracia de pocos segundos.
- Algunos errores tienen que guardar lo que se escribió antes de fallar: el evento de "login fallido" y
  la revocación de una familia por reuso. Esos errores tienen `keep_changes = True` y `get_session` hace
  commit antes de responder con el error; el resto de los errores deshace la transacción.
- Si el email no existe, el login igual verifica un hash Argon2 señuelo: tarda lo mismo que con una
  cuenta real y responde el mismo mensaje, así no se puede averiguar qué emails están registrados.
- Un access token robado sirve hasta 15 minutos. Revocar al instante requeriría una lista de tokens
  revocados, que no se justifica todavía.
- Cambiar `JWT_SECRET` invalida todos los access tokens (no los refresh tokens, que no dependen de él).

## Evidencia

Tests de la etapa 2: rotación y reuso (paso 11), cookies y CSRF (paso 13). El criterio de terminado
"reusar un refresh token ya rotado invalida la sesión" se cubre en `tests/integration/test_auth_api.py`.
Del lado del navegador, el refresh compartido y el reintento tras un 401 se prueban en
`frontend/src/lib/api/session.test.ts` y `auth-fetch.test.ts`.
