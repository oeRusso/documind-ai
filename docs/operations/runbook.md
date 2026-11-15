# Runbook de operación

Qué hacer, paso a paso, en el servidor. Todo se corre desde la carpeta del repo. Los scripts
eligen solos `docker compose` (VPS) o `podman compose` (PC). En el VPS, los comandos que llevan
`sudo` los corre Esteban (`CLAUDE.md`, «Despliegue»).

| Situación | Comando | Tiempo medido |
|---|---|---|
| Publicar la versión de `main` | `infrastructure/scripts/deploy.sh` | 30 s con caché, 3–5 min sin caché |
| Volver a la versión anterior | `infrastructure/scripts/rollback.sh` | ver «Rollback» |
| Backup ahora | `infrastructure/scripts/backup.sh` | 8 s (42 MB) |
| Restaurar el último backup | `infrastructure/scripts/restore.sh` | 5 s (42 MB) |
| Bajar los backups a la PC | `infrastructure/scripts/pull-backups.sh usuario@servidor` (en la PC) | según la conexión |

Los tiempos son de la PC de desarrollo (2026-11-15); en el VPS serán algo mayores.

---

## 0. Primer despliegue (una sola vez)

> Pendiente de verificar contra la guía del VPS compartido (`VPS-COMPARTIDO.md`, disco externo):
> ruta del repo, usuario de deploy y memoria libre. La configuración de producción ya se probó
> completa en la PC (`compose.prod.yaml`): registro cerrado, IP real desde Cloudflare, demo,
> procesamiento y respuestas.

| # | Quién | Qué |
|---|---|---|
| 1 | Esteban | En Cloudflare Zero Trust → Networks → Tunnels: crear el túnel `documind`, con el hostname público `documind.esteban-russo.com` apuntando a `http://caddy:80`. Copiar el token. |
| 2 | Esteban | Mergear `development` → `main` (PR) cuando esté todo revisado. |
| 3 | Esteban | `sudo mkdir -p /srv/documind-backups && sudo chown <usuario-deploy>: /srv/documind-backups` |
| 4 | Claude / Esteban | `git clone https://github.com/oeRusso/documind-ai.git <ruta>` y `cd <ruta>` (rama `main`). |
| 5 | Claude | `infrastructure/scripts/generate-env.sh`: crea el `.env` (600) con contraseñas aleatorias que no se muestran, y apunta los scripts a `compose.prod.yaml`. |
| 6 | Esteban | Pegar el token del paso 1 en `CLOUDFLARE_TUNNEL_TOKEN` del `.env`, y guardar `RESTIC_PASSWORD` en el gestor de contraseñas. |
| 7 | Claude | `free -h` y `docker stats --no-stream`: tienen que quedar unos 5 GB libres para DocuMind. |
| 8 | Claude | `infrastructure/scripts/deploy.sh` (construye, migra y levanta; 3–5 min la primera vez). |
| 9 | Claude | Modelos: `docker compose -f compose.prod.yaml exec ollama ollama pull bge-m3` y `... ollama pull llama3.2:3b`. |
| 10 | Claude | Demo: `docker compose -f compose.prod.yaml exec api python -m app.jobs.reset_demo`. |
| 11 | Esteban | Su cuenta: `docker compose -f compose.prod.yaml exec api python -m app.jobs.create_account <email> "<Organización>" <slug>` (pide la contraseña sin mostrarla). |
| 12 | Esteban | Backup diario en el cron (sección 3). |
| 13 | Claude | Verificar: https://documind.esteban-russo.com, «Probar la demo», `uv run python -m evaluation.eval_injection --base https://documind.esteban-russo.com --email <cuenta>` y `evaluation.load_chat --base ...` (desde la PC). |
| 14 | Esteban | Tags sobre `main`: `v0.1.0`, `v0.2.0`, `v0.3.0` y `v1.0.0` (ver `CHANGELOG.md`). |

Para los comandos a mano en el servidor, `docker compose` necesita los mismos archivos que los
scripts: `docker compose -f compose.prod.yaml --env-file .env --env-file .deploy/image.env <comando>`.

---

## 1. Deploy

Se construye en el servidor (sin registro de imágenes, ADR 0013). Cada versión queda con la
etiqueta de su commit, así la anterior sigue disponible para volver.

```bash
infrastructure/scripts/deploy.sh
```

1. `git pull --ff-only` (si `main` no avanza en línea recta, frena: nunca se fuerza).
2. Construye `documind-backend`, `documind-worker` y `documind-web` con la etiqueta del commit.
3. Guarda la etiqueta en `.deploy/image.env` y levanta todo. El servicio `migrate` aplica las
   migraciones antes de que arranque la API.
4. Anota `fecha anterior -> nueva` en `.deploy/history`.

**Verificar:** `curl -s http://127.0.0.1:8000/ready` responde `{"status":"ready"}` y
`docker compose ps` muestra `api`, `web` y `worker` como `healthy`.

## 2. Rollback

```bash
infrastructure/scripts/rollback.sh          # a la versión anterior (sale de .deploy/history)
infrastructure/scripts/rollback.sh <tag>    # a una en particular
```

Levanta las imágenes de esa versión **sin construir nada**. Antes compara las migraciones: si la
versión vieja espera menos migraciones que las que tiene la base, frena y muestra el comando para
bajar la base. Bajar una migración puede borrar datos de las tablas nuevas: decidilo mirando la
migración, y con un backup recién hecho.

Para que el rollback sea siempre posible, las migraciones se escriben en dos pasos cuando cambian
algo existente: primero se agrega (columna nueva, tabla nueva) y recién en una versión posterior se
quita lo viejo.

## 3. Backups

**Qué se guarda:** la base completa (`pg_dump`, formato custom) y los archivos subidos (volumen
`documents`). Los modelos de Ollama no: se vuelven a bajar.

**Cómo:** restic, con cifrado. Retención: 7 diarios y 4 semanales. El repositorio queda en
`BACKUP_DIR` (por defecto `backups/repo`, ignorado por git).

**Contraseña:** `RESTIC_PASSWORD` en el `.env`. **Sin ella los backups no se pueden leer.** Guardá
una copia fuera del servidor (en tu gestor de contraseñas).

**Programarlo en el VPS** (lo corre Esteban, una sola vez):

```bash
sudo crontab -u <usuario-del-deploy> -e
# todos los días a las 4:15
15 4 * * * cd /ruta/a/documind-ai && BACKUP_DIR=/srv/documind-backups/repo BACKUP_STAGING=/srv/documind-backups/staging infrastructure/scripts/backup.sh >> /srv/documind-backups/backup.log 2>&1
```

**Copia fuera del servidor**, desde la PC (sin nube; ADR 0013):

```bash
infrastructure/scripts/pull-backups.sh usuario@servidor /srv/documind-backups/repo
```

La copia sigue cifrada. Para revisarla en la PC:
`RESTIC_PASSWORD=... restic -r ~/documind-backups/repo snapshots`.

## 4. Restaurar un backup

```bash
docker compose --profile backup run --rm backup snapshots   # (opcional) ver las copias
infrastructure/scripts/restore.sh            # la última
infrastructure/scripts/restore.sh <id>       # una en particular
```

1. Detiene la API, el worker y la web.
2. Restaura el volcado de la base y los archivos. Los archivos subidos después del backup se
   borran, para que base y archivos coincidan.
3. Carga la base (`pg_restore --clean`) y levanta todo.

**En un servidor nuevo** (se perdió el VPS):

1. Instalar Docker, clonar el repo y crear el `.env` con los mismos secretos (sobre todo
   `RESTIC_PASSWORD`).
2. Copiar el repositorio de backups desde la PC al servidor (`rsync -a ~/documind-backups/repo/ servidor:/srv/documind-backups/repo/`).
3. `docker compose up -d db` y esperar a que esté `healthy` (crea los roles de la base).
4. `BACKUP_DIR=/srv/documind-backups/repo infrastructure/scripts/restore.sh`.
5. `docker compose exec ollama ollama pull bge-m3` y `ollama pull llama3.2:3b`.
6. Verificar como en el deploy, y entrar a la web con una cuenta conocida.

**Simulacro hecho el 2026-11-15** (criterio de la etapa 11): backup del entorno de desarrollo y
restauración en un entorno nuevo y vacío (`-p documind-drill`, otros puertos y volúmenes). Mismos
documentos, mismo SHA-256 de cada archivo, mismas conversaciones, mismos 156 fragmentos y RLS activo.

## 5. Rotar secretos

Todos viven en el `.env` del servidor (permisos 600). Después de cambiar cualquiera:
`docker compose up -d` (los servicios toman el valor nuevo al reiniciarse).

| Secreto | Efecto de cambiarlo | Pasos |
|---|---|---|
| `JWT_SECRET` | Todas las sesiones se cierran (hay que volver a entrar) | Generar uno nuevo (`openssl rand -base64 48`), reemplazar, `up -d` |
| `APP_DB_PASSWORD` / `MIGRATOR_DB_PASSWORD` | Ninguno si se hace en orden | `docker compose exec db psql -U postgres -c "ALTER ROLE app PASSWORD '<nueva>'"`, después cambiarla en `.env` y `up -d` |
| `POSTGRES_PASSWORD` | Ninguno | `ALTER ROLE postgres PASSWORD '<nueva>'` y `.env` |
| `GRAFANA_ADMIN_PASSWORD` | Solo el login de Grafana | `docker compose exec grafana grafana cli admin reset-admin-password '<nueva>'` y `.env` |
| `RESTIC_PASSWORD` | Los backups viejos siguen con la vieja | `restic key add` con la nueva y `restic key remove` de la vieja (con el servicio `backup`), después `.env` |
| Token del túnel de Cloudflare | El sitio se corta hasta reemplazarlo | Lo regenera Esteban en Cloudflare y lo carga en `.env` |

## 6. Problemas comunes

| Síntoma | Mirar | Arreglo |
|---|---|---|
| La web carga pero preguntar da error | `docker compose logs api \| grep -i llm` | ¿Está el modelo? `docker compose exec ollama ollama list` |
| Documentos trabados en «Procesando» | Grafana → «Cola y documentos»; `docker compose logs worker` | Se re-encolan solos al consultar el estado; si no, `docker compose restart worker` |
| RAM alta (alerta) | `free -h`, `docker stats --no-stream` | Apagar el monitoreo (`--profile monitoring stop`) o bajar `LLM_KEEP_ALIVE` |
| Disco lleno | `df -h`, `docker system df` | `docker image prune` (deja las imágenes en uso; borra versiones viejas: elegí cuántas guardar) |
