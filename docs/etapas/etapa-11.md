# Etapa 11 — Producción robusta

- **Fase:** D — Producción y portfolio
- **Duración estimada:** 3 a 5 días
- **Rama:** `development` (PR a `main` al cerrar la etapa)
- **Estado:** terminada en local (2026-11-15), en `development`; lo del VPS va con el despliegue final

## Objetivo

Que el sistema sobreviva a un error tuyo, a un disco lleno o a la pérdida del VPS.

## Tareas

- [x] Backups diarios cifrados con restic ~~hacia Cloudflare R2~~ (sin nube: repositorio en el servidor + copia en la PC por `rsync`, ADR 0013): volcado de PostgreSQL y archivos de documentos, con retención de 7 diarios y 4 semanales.
- [x] Límites de CPU y memoria, healthchecks y reinicio automático en todos los contenedores (Quadlet con systemd si querés aprenderlo).
- [x] Rotación de logs.
- [x] Cabeceras de seguridad en Caddy ~~y reglas de rate limiting en Cloudflare~~ (rate limiting en la app, ADR 0013).
- [x] Runbook en `docs/operations/`: deploy, rollback a la imagen anterior, restauración de backup, rotación de secretos.

## Fuera de alcance

- Alta disponibilidad o múltiples VPS (monolito en un solo VPS por diseño).
- Almacenamiento S3 para documentos (extensión post v1).

## Criterios de terminado

- [x] Restauraste la base y los archivos en un entorno limpio siguiendo solo el runbook.
- [x] Un rollback a la versión anterior lleva menos de 5 minutos. **9,1 s en la PC; repetir en el VPS.**

## Notas

- Revisar los límites del plan gratuito de R2 al activarlo (los planes gratis cambian).
- **Regla de servicios externos** (`CLAUDE.md`): R2 y las reglas de rate limiting de Cloudflare requieren permiso
  de Esteban. Hay que definir otro destino de backups fuera del VPS o pedir autorización.

- **Lo que deja la etapa 10** (ADR 0012): Prometheus y Grafana en el perfil `monitoring`, con alertas
  por email. Los límites de memoria de los servicios de monitoreo ya están; faltan los del resto.

## Resultado

**Criterios:** restauración en un entorno limpio siguiendo el runbook (5 s, datos idénticos) y
rollback en 9,1 s. Los dos medidos en la PC; se repiten en el VPS con el despliegue (ADR 0013).

**Qué quedó:**

- `compose.yaml`: límites de memoria y CPU, healthchecks, reinicio y logs rotados en todos los
  servicios; imágenes con `IMAGE_TAG`; puertos configurables (para un entorno de prueba aparte);
  servicio `backup` (restic, perfil `backup`) y `caddy` (perfil `proxy`, http://127.0.0.1:8080).
- `infrastructure/scripts/`: `deploy.sh`, `rollback.sh`, `backup.sh`, `restore.sh`,
  `pull-backups.sh` y `lib.sh` (elige Podman en la PC y Docker en el VPS).
- `infrastructure/proxy/Caddyfile`: cabeceras de seguridad, rutas privadas cerradas y streaming sin
  retener.
- `docs/operations/runbook.md`: deploy, rollback, backups, restauración (también en un servidor
  nuevo), rotación de secretos y problemas comunes.
- Imágenes: el backend aplica los parches de Debian y la web no lleva npm (etapa 9).

**Pendientes (con el despliegue):**

- Programar `backup.sh` en el cron del VPS y `pull-backups.sh` en la PC.
- Repetir el simulacro de restauración y el rollback en el VPS.
- Quadlet no se usó: el VPS ya funciona con Docker Compose.

## Referencias

- Parte 1: §7 (fila Continuidad).
