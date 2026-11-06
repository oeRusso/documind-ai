# Etapa 2 — Autenticación, organizaciones y multi-tenancy

- **Fase:** A — Fundamentos
- **Duración estimada:** 1,5 semanas
- **Rama:** `development` (PR a `main` al cerrar la etapa)
- **Estado:** en curso

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
- [ ] Rate limit en login y registro; campo trampa (honeypot) en el registro. *(Sin Turnstile: ADR 0005.)*
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

## Plan de implementación (aprobado el 2026-11-06)

### Decisiones

- La organización activa viaja en el header `X-Organization-Id`; la membresía y el rol se leen de la base en cada request (ADR 0003).
- RLS con dos variables por transacción (`app.current_user`, `app.current_org`), fijadas con `set_config(..., true)`.
  `users` y `refresh_tokens` son tablas de identidad: sin `organization_id` ni RLS (ADR 0003).
- Access token en memoria del navegador; refresh token rotativo en cookie `HttpOnly; Secure; SameSite=Lax; Path=/api/v1/auth`;
  CSRF con chequeo de `Origin` + doble envío (`csrf_token` / `X-CSRF-Token`) (ADR 0004).
- En desarrollo, Next.js reenvía `/api/*` al backend (rewrites): mismo origen, sin CORS.
- El registro crea usuario + organización + membresía owner en una sola transacción.
- Emails de invitación con `BackgroundTasks` hasta la etapa 5 (Celery); el link también se devuelve al admin,
  así que si el email falla no se pierde nada.
- Rate limit en memoria detrás de una interfaz `RateLimiter` (se pasa a Valkey en la etapa 5).
- Sin Turnstile (decisión de Esteban, ADR 0005): campo trampa en el registro + rate limit.
- Las piezas críticas (RLS, rotación de tokens, permisos) las escribe Claude y la persona las revisa.

### Pasos

- [x] 1. ADR 0003 (multi-tenancy y RLS) y 0004 (sesiones y tokens).
- [x] 2. Configuración nueva (`JWT_SECRET`, `ACCESS_TOKEN_MINUTES`, `REFRESH_TOKEN_DAYS`, `APP_ORIGIN`).
  `SMTP_*`/`MAIL_FROM` entran en el paso 19, junto con el código que las usa. `TURNSTILE_*` no entra (ADR 0005).
- [x] 3. Migración 0002: tablas de identidad (sin RLS) y modelos.
- [x] 4. RLS I: contexto por transacción + políticas de `organizations` y `memberships`; limpieza de tests con `migrator`.
- [x] 5. RLS II: `invitations` y `audit_logs` (solo inserción). *(Hecho junto con el 4: migración 0003.)*
- [ ] 6. Módulo `audit`: `RecordAuditEvent`.
- [ ] 7. Módulo `users`: entidad, política de contraseña, Argon2id, repositorio.
- [ ] 8. Tokens: JWT de acceso (PyJWT) y refresh token opaco con hash.
- [ ] 9. Roles y matriz de permisos; repositorio de memberships.
- [ ] 10. Casos de uso `Register` y `Login`.
- [ ] 11. `RefreshSession` (rotación y detección de reuso) y `Logout`.
- [ ] 12. Router de auth I: register, login, me; errores 401 y 403.
- [ ] 13. Router de auth II: refresh y logout con cookie y CSRF.
- [ ] 14. Dependencia `CurrentMember` y endpoints de `organizations` rehechos.
  (Los endpoints sin autenticación de la etapa 1 se quitaron en el paso 4: con RLS no pueden funcionar.)
- [ ] 15. Test de aislamiento con el filtro del backend deshabilitado.
- [ ] 16. Miembros: listar, cambiar rol, quitar.
- [ ] 17. Invitaciones: crear, listar, revocar.
- [ ] 18. Aceptar invitación.
- [ ] 19. Mailpit y `Mailer`.
- [ ] 20. Rate limit.
- [ ] 21. Campo trampa (honeypot) en el registro (en lugar de Turnstile, ADR 0005).
- [ ] 22. Frontend: Next.js, Vitest, rewrites y CI.
- [ ] 23. Frontend: cliente generado del OpenAPI con refresh compartido.
- [ ] 24. Frontend: shadcn/ui, sesión, login y registro.
- [ ] 25. Frontend: selector de organización.
- [ ] 26. Frontend: miembros, invitaciones y aceptar invitación.
- [ ] 27. Cierre: README, ADRs aceptadas, Resultado, PR.

## Referencias

- Parte 1: §5 (entidades de la etapa 2, aislamiento en dos capas), §7 (contraseñas, cookies, autorización, abuso).
