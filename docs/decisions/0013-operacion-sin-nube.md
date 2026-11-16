# 0013 — Operación sin nube: deploy en el servidor, backups con restic y rollback por etiquetas

- **Estado:** aceptada
- **Fecha:** 2026-11-15
- **Etapa:** 11

## Contexto

El plan proponía GitHub Container Registry para las imágenes, Cloudflare R2 para los backups y
reglas de rate limiting en Cloudflare. Esteban decidió (2026-11-15) no sumar servicios externos y
hacer todo en local primero. El VPS es compartido (8 GB) y se despliega a mano desde `main`.

## Opciones consideradas

**Imágenes y deploy**
1. GitHub Actions + GHCR + deploy por SSH: más automático, pero agrega un registro y llaves de
   deploy en GitHub.
2. **Construir en el VPS** (`git pull` + `compose build`), con las imágenes etiquetadas por commit.

**Backups fuera del servidor**
1. restic hacia Cloudflare R2: servicio externo.
2. **restic a un repositorio en el VPS, y la PC lo baja con `rsync`**: cifrado, sin nube; depende de
   que la PC lo baje seguido.

**Rate limiting**
1. Reglas de Cloudflare: servicio externo.
2. Plugin de Caddy: requiere compilar Caddy a medida.
3. **En la app** (ya existe: login, registro, invitaciones, chat) y Caddy limita el tamaño de los pedidos.

**Supervisión de contenedores:** Quadlet con systemd (opcional en el plan) o **Compose con
`restart`, healthchecks y límites**. El VPS ya usa Docker Compose para el portfolio.

## Decisión

Opción 2 en imágenes y backups, opción 3 en rate limiting, y Compose para la supervisión.

- `deploy.sh` etiqueta las imágenes con el commit y guarda la etiqueta en `.deploy/image.env`.
  `rollback.sh` levanta las imágenes anteriores sin construir, y frena si la versión vieja espera
  otras migraciones.
- `backup.sh`: `pg_dump` + volumen de documentos a restic, con 7 diarios y 4 semanales.
  `restore.sh` restaura base y archivos. `pull-backups.sh` corre en la PC.
- Todos los servicios tienen límite de memoria, reinicio, logs rotados (3 × 10 MB) y healthcheck
  donde pueden responder uno.
- Caddy: cabeceras de seguridad (HSTS, nosniff, DENY, Permissions-Policy), `/metrics` y la
  documentación de la API cerrados hacia afuera, sin comprimir `text/event-stream` y con
  `flush_interval -1` para que la respuesta llegue de a pedazos.

## Consecuencias

- Un deploy usa CPU del VPS mientras construye (3–5 min sin caché). Si molesta al portfolio, se
  puede pasar a GHCR más adelante (decisión de Esteban).
- Las imágenes viejas ocupan disco: el runbook explica cómo podarlas.
- Si la PC no baja los backups, la única copia está en el VPS: conviene programar `pull-backups.sh`
  en la PC (cron o un recordatorio).
- `RESTIC_PASSWORD` es crítica: sin ella los backups no sirven. Va en el gestor de contraseñas.
- Rollback con migraciones distintas requiere bajar la base a mano: por eso las migraciones que
  cambian algo existente se hacen en dos pasos (agregar primero, quitar después).

## Evidencia

Medido en la PC (2026-11-15), ver `docs/operations/runbook.md`:

- Backup del entorno de desarrollo: 42 MB en 8 s; `restic check` sin errores.
- **Restauración en un entorno nuevo y vacío** (`-p documind-drill`): 5 s; mismos documentos, mismo
  SHA-256 de cada archivo, mismas conversaciones, 156 fragmentos y RLS activo.
- **Rollback** a la versión anterior: 9,1 s hasta que la API y la web responden (criterio: < 5 min).
- Respuesta en streaming a través de Caddy: 19 pedazos entre los segundos 15,4 y 17,2, sin compresión.
