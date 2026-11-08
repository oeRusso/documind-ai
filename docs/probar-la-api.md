# Probar la API a mano (desarrollo)

## 1. Levantar todo y cargar los datos de prueba

```bash
podman compose up -d --build
podman compose exec api python -m app.dev.seed
```

El segundo comando crea usuarios de prueba. Si ya estaban cargados, no hace nada.

| Servicio | Dirección |
|---|---|
| API con Swagger (para probar endpoints) | http://127.0.0.1:8000/docs |
| Mailpit (emails de desarrollo) | http://127.0.0.1:8025 |

## 2. Usuarios de prueba

Contraseña de todos: **`documind-demo-2026`** (es pública: solo sirve en tu PC).

| Email | Organización | Rol | Qué puede hacer |
|---|---|---|---|
| `ana@acme.test` | Acme S.A. | owner | Todo |
| `carla@acme.test` | Acme S.A. | admin | Invitar y manejar a member y viewer |
| `mario@acme.test` | Acme S.A. | member | Ver miembros |
| `bob@acme.test` | Acme S.A. | viewer | Ver miembros |
| `eve@globex.test` | Globex | owner | Todo, pero en Globex: Acme no existe para ella |

## 3. Cómo usar Swagger

1. **Entrar:** `POST /api/v1/auth/login` → "Try it out" → `{"email": "ana@acme.test", "password": "documind-demo-2026"}`. <!-- pragma: allowlist secret -->
   Copiá el `access_token` de la respuesta.
2. **Autorizar:** botón **Authorize** (arriba a la derecha) → pegá el token → Authorize.
   El token dura 15 minutos; si da 401, repetí el login.
3. **Elegir la organización:** `GET /api/v1/organizations` → copiá el `id`.
   Los endpoints de miembros e invitaciones lo piden en el campo **`X-Organization-Id`**.

Para cambiar de usuario: Authorize → Logout → login con otro email → Authorize con el nuevo token.

## 4. Qué probar

| Para ver… | Usuario | Endpoint | Resultado esperado |
|---|---|---|---|
| Mis organizaciones y mi rol | cualquiera | `GET /organizations` | 200 |
| Miembros de Acme | cualquiera de Acme | `GET /members` | 200 con 4 personas |
| **Un viewer no puede hacer acciones de admin** | bob | `PATCH /members/{id de mario}` con `{"role": "viewer"}` | **403** `forbidden` |
| Un admin cambia un rol menor | carla | `PATCH /members/{id de bob}` con `{"role": "member"}` | 200 |
| Un admin no puede tocar al owner | carla | `PATCH /members/{id de ana}` con `{"role": "viewer"}` | 403 |
| No quedarse sin owner | ana | `PATCH /members/{id de ana}` con `{"role": "admin"}` | **409** `last_owner` |
| **Otra organización no existe** | eve | `GET /members` con el id de Acme | **404** `organization_not_found` |
| Invitar | ana o carla | `POST /invitations` con `{"email": "dana@acme.test", "role": "viewer"}` | 201 con `link`; el email aparece en Mailpit |
| Ver invitaciones abiertas | ana o carla | `GET /invitations` | 200 |
| Revocar una invitación | ana o carla | `DELETE /invitations/{id}` | 204 |

### Aceptar una invitación

El link tiene esta forma: `http://localhost:3000/invitations/accept#organization=<id>&token=<token>`.
Esa página es del frontend, que todavía no existe. Por ahora, copiá los dos valores que están después del `#`:

- **Si la persona no tiene cuenta:** `POST /auth/register` (sin token) con
  `{"email": "dana@acme.test", "password": "una clave de 10 o más", "invitation": {"organization_id": "<id>", "token": "<token>"}}`. <!-- pragma: allowlist secret -->
  Entra a Acme con el rol de la invitación.
- **Si ya tiene cuenta:** login con esa cuenta, Authorize, y `POST /invitations/accept` con
  `{"organization_id": "<id>", "token": "<token>"}`.

Probá también: usar el mismo link dos veces (404), o registrarte con otro email (403 `invitation_email_mismatch`).

## 5. Empezar de cero

```bash
podman compose down -v   # borra también la base de datos
podman compose up -d --build && podman compose exec api python -m app.dev.seed
```
