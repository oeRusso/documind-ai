# Etapa 3 — Primer deploy y CI/CD

- **Fase:** A — Fundamentos (cierra con el tag `v0.1.0`)
- **Duración estimada:** 3 a 4 días
- **Rama:** `development` (PR a `main` al cerrar la etapa)
- **Estado:** en producción desde el 2026-11-16; faltan pendientes de Esteban (ver «Resultado parcial»)

## Objetivo

Que cada merge a `main` llegue solo a producción, desde ahora y para siempre.

## Tareas

- [ ] Imagen de Next.js con salida `standalone`.
- [ ] `compose.prod.yaml` con Caddy, API, web y PostgreSQL en una red interna.
- [ ] Cloudflare Tunnel: `cloudflared` conecta el VPS con Cloudflare y enruta `app.tudominio` a Caddy. Configuración en `infrastructure/tunnel/`.
- [ ] Caddy (`infrastructure/proxy/Caddyfile`) reparte `/api` al backend y el resto al frontend.
- [ ] Cloudflare Access listo para proteger paneles y la demo privada.
- [ ] GitHub Actions: build de imágenes, push a GitHub Container Registry, deploy por SSH (`pull`, `alembic upgrade head`, `up -d`).
- [ ] Secretos solo en GitHub Secrets y en un `.env` del VPS con permisos 600.
- [ ] Backup diario con `pg_dump` en el VPS.
- [ ] Monitoreo externo con UptimeRobot (o equivalente externo al VPS).

## Fuera de alcance

- Backups cifrados fuera del VPS con restic + R2 (etapa 11).
- Valkey, workers y Ollama en producción (etapas 5 a 7).
- Prometheus, Grafana y alertas (etapa 10).
- Cabeceras de seguridad en Caddy, rate limiting en Cloudflare y Quadlet (etapa 11).
- Runbook completo en `docs/operations/` (etapa 11).

## Criterios de terminado

- [ ] Un merge a `main` está en producción en menos de 10 minutos sin tocar el VPS.
- [ ] `https://app.tudominio` muestra el login, y un escaneo externo no encuentra puertos abiertos salvo SSH.
- [ ] Restauraste un backup en una base vacía al menos una vez.

## Notas

- Al cerrar esta etapa termina la Fase A: tag `v0.1.0`.
- **VPS compartido** (la guía del VPS compartido (ver "Despliegue" en `CLAUDE.md`)). Cambios respecto de las tareas de arriba:
  - Dirección `https://documind.esteban-russo.com`; túnel `documind` con ruta a `http://caddy:80`. El túnel lo crea Esteban.
  - Docker + Compose v2 en el VPS (sin `:Z` en volúmenes); ningún puerto publicado; `mem_limit` en los servicios.
  - **A decidir con Esteban (regla de servicios externos):** Cloudflare Access, UptimeRobot y el deploy desde
    GitHub Actions + GHCR. La guía propone construir en el VPS (`git pull --ff-only && docker compose up -d --build`).
- **IP real del cliente (de la etapa 2):** `get_client_ip` (`backend/app/core/dependencies.py`) usa la IP
  de la conexión. Detrás de Caddy y Cloudflare esa IP es la del proxy: hay que pasar a confiar en
  `CF-Connecting-IP`, y solo cuando el pedido viene del proxy. Si no, **todos los usuarios comparten el
  mismo contador** de intentos de login y registro (rate limit) y el audit log registra la IP equivocada.
- **Email en producción (de la etapa 2):** no hay servidor SMTP. Sumar uno es un servicio externo: preguntar.

- **Lo que deja la etapa 11** (ADR 0013, hecha en local antes que esta): `Caddyfile` listo,
  `deploy.sh` / `rollback.sh` (construir en el VPS, imágenes por commit), backups con restic y el
  runbook. Falta el `compose` de producción (Docker, sin `:Z`, sin puertos publicados, `cloudflared`).

- **Preparado en local (2026-11-15)**, antes del despliegue: `compose.prod.yaml` (Docker, sin
  puertos, `cloudflared`, límites de memoria, `REGISTRATION_OPEN=false`, IP real desde
  `CF-Connecting-IP`), `generate-env.sh`, `app.jobs.create_account` y la sección «Primer
  despliegue» del runbook. Probado entero en la PC como proyecto aparte. Falta: la guía
  `VPS-COMPARTIDO.md`, el túnel y el acceso al VPS.

## Resultado parcial (2026-11-16)

**En producción:** https://documind.esteban-russo.com (commit `f229804`, PR #15).

- VPS compartido, como pide la guía (`~/portfolio/docs/VPS-COMPARTIDO.md` en el servidor): repo en
  `~/documind`, `.env` 600 generado allá, imágenes construidas en el VPS (1 min 49 s), sin GHCR.
- Túnel `documindia` (así quedó el nombre; no afecta), ruta `documind.esteban-russo.com` →
  `http://caddy:80`, CNAME creado por Cloudflare. El token se pegó sin pasar por el chat.
- Modelos `bge-m3` y `llama3.2:3b`; demo cargada (4 leyes, ~8 min de procesamiento en CPU).
- Verificado: login, «Probar la demo», respuesta con cita (Ley 20.744, págs. 19–20); la cuenta demo
  recibe 403 al crear organización, subir, borrar, reprocesar, invitar o cambiar roles, y 404 con otra
  organización; desde internet no responde ningún puerto (80, 443, 3000, 5432, 6379, 8000, 11434).
  El portfolio siguió `healthy` durante todo el deploy.
- Backup real con restic (2,6 MiB, 18 s). Arreglo: con Docker restic escribe como `root`;
  `BACKUP_OWNER` le devuelve el repositorio al usuario del deploy (si no, `pull-backups.sh` no lo lee).
- **Latencia en CPU:** el VPS lee el prompt a ~26 tokens/s y genera a ~6,5 tokens/s. Una pregunta
  nueva (~1500 tokens de contexto) tarda ~1 min hasta la primera palabra; repetida, 15 s.

**Pendientes:**
- Esteban: guardar `RESTIC_PASSWORD` fuera del servidor, crear su cuenta (`app.jobs.create_account`),
  cron del backup (`crontab -e`, sin `sudo`), tags sobre `main`.
- Simulacros en el VPS: inyección (con la cuenta de Esteban), restore, rollback y carga.
- Mientras espera la primera palabra, el chat no muestra la pregunta ni un indicador: revisar en el frontend.
- Medir si menos fragmentos en el contexto bajan la latencia sin empeorar `eval_answers`.
- El login muestra «Creá una para tu empresa» con el registro cerrado (la API lo rechaza igual).
- Criterio «un merge a `main` está en producción sin tocar el VPS»: hoy el deploy es `deploy.sh` a mano (ADR 0013).

## Referencias

- Parte 1: §2 (arquitectura), §7 (red, secretos, continuidad), §8 (CI, paso 5).
- Parte 2: "Servicios gratuitos de terceros".

- **Streaming del chat (descubierto en la etapa 7):** cualquier compresión entre la API y el navegador
  puede retener una respuesta SSE (`text/event-stream`) hasta el final, y el chat mostraría todo el texto
  de golpe. Next.js ya tiene `compress: false`. En Caddy, no comprimir `text/event-stream` (o usar
  `flush_interval -1` en el `reverse_proxy`) y verificar con
  `curl -N --compressed` que los eventos `token` llegan de a uno.
