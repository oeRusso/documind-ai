# Probar la API a mano (desarrollo)

## 1. Levantar todo y cargar los datos de prueba

```bash
podman compose up -d --build
podman compose exec api python -m app.dev.seed
```

El segundo comando crea usuarios de prueba. Si ya estaban cargados, no hace nada.

| Servicio | Dirección |
|---|---|
| **Web** (usá `localhost`, no `127.0.0.1`) | http://localhost:3000 |
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

## 3. Desde la web

1. Entrá a http://localhost:3000 con `ana@acme.test`: ves los 4 miembros de Acme y podés cambiar roles.
2. **Invitaciones** → invitá a `dana@acme.test` como Lector. Aparece el link y el email llega a Mailpit.
3. **Salir**, abrí el link (desde Mailpit o copiado) y creá la cuenta de dana: entra a Acme como Lector.
4. Entrá como `bob@acme.test` (viewer): ve los miembros, pero sin controles ni menú de invitaciones.
5. Entrá como `eve@globex.test`: solo ve Globex. Acme no existe para ella.
6. Recargá la página: la sesión sigue (se renueva sola con la cookie).

## 4. Cómo usar Swagger

1. **Entrar:** `POST /api/v1/auth/login` → "Try it out" → `{"email": "ana@acme.test", "password": "documind-demo-2026"}`. <!-- pragma: allowlist secret -->
   Copiá el `access_token` de la respuesta.
2. **Autorizar:** botón **Authorize** (arriba a la derecha) → pegá el token → Authorize.
   El token dura 15 minutos; si da 401, repetí el login.
3. **Elegir la organización:** `GET /api/v1/organizations` → copiá el `id`.
   Los endpoints de miembros e invitaciones lo piden en el campo **`X-Organization-Id`**.

Para cambiar de usuario: Authorize → Logout → login con otro email → Authorize con el nuevo token.

## 5. Qué probar en Swagger

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
Lo más simple es abrirlo en el navegador. Para hacerlo por Swagger, copiá los dos valores que están después del `#`:

- **Si la persona no tiene cuenta:** `POST /auth/register` (sin token) con
  `{"email": "dana@acme.test", "password": "una clave de 10 o más", "invitation": {"organization_id": "<id>", "token": "<token>"}}`. <!-- pragma: allowlist secret -->
  Entra a Acme con el rol de la invitación.
- **Si ya tiene cuenta:** login con esa cuenta, Authorize, y `POST /invitations/accept` con
  `{"organization_id": "<id>", "token": "<token>"}`.

Probá también: usar el mismo link dos veces (404), o registrarte con otro email (403 `invitation_email_mismatch`).

### Documentos (etapa 4)

En la web es lo más cómodo: **Documentos** (es la página de inicio) → arrastrá archivos a la zona punteada.

| Para ver… | Cómo | Resultado esperado |
|---|---|---|
| Subir | Un PDF, DOCX, TXT o Markdown | Aparece en la lista como "Pendiente de procesar" (el procesamiento llega en la etapa 5) |
| **Un `.exe` renombrado a `.pdf`** | Renombrá cualquier programa a `algo.pdf` y subilo | **"Tipo de archivo no permitido"** (415) |
| PDF con contraseña | Un PDF que pida clave para abrirse | "El archivo está protegido con contraseña" |
| **Duplicado** | El mismo archivo otra vez (aunque tenga otro nombre) | **"Este archivo ya está cargado en…"** con link al existente (409) |
| Versión nueva | Entrá al documento → "Subir versión nueva" | Aparece como v2; la v1 se sigue pudiendo descargar |
| **Otra organización** | Entrá como `eve@globex.test`, o por Swagger `GET /documents/{id}` con el id de un documento de Acme y la organización de Globex | No aparece en la lista; por API, **404** `document_not_found` |
| Lector | Entrá como `bob@acme.test` | Ve y descarga, pero no tiene zona de subida ni botón Borrar |
| Borrar | Como `mario` (miembro) intentá borrar un documento de `ana` por Swagger | 403 `cannot_delete_document`; el suyo sí lo puede borrar |

En Swagger, `POST /documents` tiene un botón para elegir el archivo. La descarga (`GET /documents/{id}/download`)
devuelve el archivo; un borrado lo oculta al instante y el archivo se elimina del disco a los 30 días
(`podman compose exec api python -m app.jobs.purge_documents`).

### Procesamiento (etapa 5)

Después de subir un documento, entrá a su detalle: el panel **Procesamiento** muestra los pasos en vivo
(En cola → Leyendo el texto → Reconociendo páginas escaneadas → Armando fragmentos → Listo). Abajo aparecen
los **Fragmentos**, cada uno con su sección y su página.

| Para ver… | Cómo | Resultado esperado |
|---|---|---|
| OCR | Subí `backend/tests/fixtures/escaneado.pdf` (una imagen, sin texto) | Fragmento con "El personal deberá usar casco…" y "1 con OCR" |
| Cortes por cláusula | Subí `backend/tests/fixtures/contrato.pdf` | 3 fragmentos, uno por cláusula, cada uno con su página; sin el encabezado ni "Página N de 3" |
| Word con tabla | `backend/tests/fixtures/politica.docx` | La tabla aparece como "CABA \| $30.000" dentro de "Montos diarios" |
| Worker caído | `podman compose stop worker`, subí algo, `podman compose start worker` | Queda "En cola" y se procesa solo al volver el worker |
| Reprocesar | Botón **Reprocesar** en el detalle | Vuelve a correr y los fragmentos se reemplazan (no se duplican) |
| Tiempos | `podman compose logs worker` | Líneas `page_extracted` / `page_ocr` con `ms` por página |

### Búsqueda (etapa 6)

Menú **Búsqueda**. Para tener contenido real, subí alguna ley de `backend/evaluation/corpus/` (por ejemplo
`ley-20744-contrato-de-trabajo.pdf`) y esperá a que quede «Listo» (el paso "Preparando la búsqueda" calcula
los embeddings).

| Probá | Resultado esperado |
|---|---|
| «¿cuántos días de vacaciones me corresponden si tengo 3 años de antigüedad?» | Primero el art. 150 (pág. 37), "catorce (14) días corridos" |
| «art. 245 LCT indemnización» | El art. 245 entre los primeros (los términos exactos los encuentra la parte "por palabras") |
| La misma pregunta en modo **Por palabras** y **Por significado** | Cada resultado muestra su posición en cada ranking |
| «informacion publica» (sin tildes) | Encuentra "información pública" |
| Entrá como `eve@globex.test` y buscá lo mismo | Nada: los documentos de Acme no existen para Globex |

Por API: `GET /api/v1/search?q=...&mode=hybrid|vector|text&limit=10` (con `X-Organization-Id`).

Para medir la calidad (en `backend/`): `uv run python -m evaluation.eval_retrieval`.

### Preguntar (etapa 7)

Menú **Preguntar**. Usa los mismos documentos que la búsqueda y el modelo `llama3.2:3b`
(`podman compose exec ollama ollama pull llama3.2:3b` si todavía no está). En CPU, la respuesta empieza a
aparecer a los 10–20 segundos.

| Probá | Resultado esperado |
|---|---|
| «¿Cuánto dura el período de prueba?» (con la ley 20.744 cargada) | Respuesta que se va escribiendo, con una marca [1] que lleva a la fuente (ley 20.744, art. 92 bis) |
| «¿Quién ganó el mundial de 1986?» | «No encontré evidencia en los documentos…» al instante (no llama al modelo) |
| Botón **Detener** mientras escribe | Se corta y dice «Detuviste la respuesta» |
| Dos pestañas preguntando a la vez | La segunda muestra «En espera: sos la próxima pregunta» y después responde |
| Entrá como `eve@globex.test` y preguntá lo mismo | «No encontré evidencia»: los documentos de Acme no existen para Globex |
| `podman compose logs api \| grep answer_generated` | Cada respuesta con sus citas (documento, páginas y fragmentos) |

Por API: `POST /api/v1/chat` con `{"question": "..."}` y `X-Organization-Id`. La respuesta es un stream
de eventos `queued`, `token`, `citations` y `done` (en Swagger se ve todo junto al final; con
`curl -N` se ve llegar).

Para medir (en `backend/`): `OLLAMA_URL=http://127.0.0.1:11435 uv run python -m evaluation.eval_answers`
(unos 40 minutos) y `uv run python -m evaluation.load_chat` (5 preguntas a la vez).

## 6. Empezar de cero

```bash
podman compose down -v   # borra también la base de datos y los archivos subidos
podman compose up -d --build && podman compose exec api python -m app.dev.seed
```
