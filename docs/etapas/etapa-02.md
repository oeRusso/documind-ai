# Etapa 2 — Autenticación, organizaciones y multi-tenancy

- **Fase:** A — Fundamentos
- **Duración estimada:** 1,5 semanas
- **Rama:** `development` (PR a `main` al cerrar la etapa)
- **Estado:** pendiente

## Objetivo

Que ninguna organización pueda ver datos de otra, garantizado por dos capas independientes.

## Tareas

- [ ] Tablas `users`, `memberships`, `refresh_tokens`, `invitations` y `audit_logs` (`organizations` ya existe desde la etapa 1).
- [ ] Roles owner, admin, member y viewer, verificados en cada caso de uso.
- [ ] Contraseñas con Argon2id (argon2-cffi).
- [ ] Access token JWT de 15 minutos; refresh token rotativo, revocable y guardado en cookie HttpOnly, Secure, SameSite=Lax. Reusar un refresh token ya rotado invalida toda la familia.
- [ ] Protección CSRF en los endpoints que usan cookies.
- [ ] Dependencia de FastAPI que resuelve el usuario y su membresía, y entrega el `organization_id` a cada caso de uso. Los repositorios lo exigen como parámetro obligatorio.
- [ ] Row Level Security en PostgreSQL: la app fija `app.current_org` por transacción (`SET LOCAL`) y usa un rol de base de datos que no puede saltarse RLS.
- [ ] Invitaciones por link.
- [ ] Rate limit en login y registro; Cloudflare Turnstile en el registro.
- [ ] `audit_logs` con las acciones de seguridad (solo inserción).
- [ ] Mailpit en `compose.yaml` para ver los emails de desarrollo (invitaciones).
- [ ] Frontend mínimo en Next.js: registro, login, selector de organización y gestión de miembros, con un cliente TypeScript generado desde el OpenAPI y TanStack Query.

## Fuera de alcance

- SSO, login social, facturación (backlog post v1).
- Reset de contraseña por email y email transaccional en producción (no están en el plan de la etapa).
- Deploy a producción (etapa 3).
- Documentos y cualquier tabla de negocio aparte de las de identidad (etapa 4 en adelante).
- Rate limit del chat (etapa 7).

## Criterios de terminado

- [ ] Un test demuestra que un usuario de la organización A no lee datos de B, incluso con el filtro del backend deshabilitado (lo frena RLS).
- [ ] Reusar un refresh token ya rotado invalida la sesión.
- [ ] Un viewer recibe 403 al intentar acciones de admin.

## Notas

- **403 vs 404**: el 403 es para falta de permiso por rol dentro de la propia organización. Un recurso de otra organización siempre responde 404.
- **Turnstile**: la Parte 1 lo pone en el registro y la tabla de servicios de la Parte 2 dice "registro y login". Mínimo: registro. Agregarlo en el login es opcional.
- **`.gitkeep` en `frontend/`**: `create-next-app` falla si ya existe `frontend/src/`. Borrar los `.gitkeep` de `frontend/` (o generar en una carpeta temporal y mover) antes de correrlo, con la opción `--src-dir`.
- **Dónde vive el access token** en el frontend (memoria, cookie) no está definido en los planes: decidirlo en el plan de la etapa y, si conviene, en una ADR.
- Variables de entorno que entran: `JWT_SECRET`, `ACCESS_TOKEN_MINUTES`, `REFRESH_TOKEN_DAYS`, `TURNSTILE_SECRET`. Probablemente también `SMTP_*` (Mailpit), `TURNSTILE_SITE_KEY` y `NEXT_PUBLIC_API_URL`.

## Referencias

- Parte 1: §5 (entidades de la etapa 2, aislamiento en dos capas), §7 (contraseñas, cookies, autorización, abuso).
