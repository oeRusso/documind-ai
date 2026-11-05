# Etapa 11 — Producción robusta

- **Fase:** D — Producción y portfolio
- **Duración estimada:** 3 a 5 días
- **Rama:** `development` (PR a `main` al cerrar la etapa)
- **Estado:** pendiente

## Objetivo

Que el sistema sobreviva a un error tuyo, a un disco lleno o a la pérdida del VPS.

## Tareas

- [ ] Backups diarios cifrados con restic hacia Cloudflare R2: volcado de PostgreSQL y archivos de documentos, con retención de 7 diarios y 4 semanales.
- [ ] Límites de CPU y memoria, healthchecks y reinicio automático en todos los contenedores (Quadlet con systemd si querés aprenderlo).
- [ ] Rotación de logs.
- [ ] Cabeceras de seguridad en Caddy y reglas de rate limiting en Cloudflare.
- [ ] Runbook en `docs/operations/`: deploy, rollback a la imagen anterior, restauración de backup, rotación de secretos.

## Fuera de alcance

- Alta disponibilidad o múltiples VPS (monolito en un solo VPS por diseño).
- Almacenamiento S3 para documentos (extensión post v1).

## Criterios de terminado

- [ ] Restauraste la base y los archivos en un entorno limpio siguiendo solo el runbook.
- [ ] Un rollback a la versión anterior lleva menos de 5 minutos.

## Notas

- Revisar los límites del plan gratuito de R2 al activarlo (los planes gratis cambian).

## Referencias

- Parte 1: §7 (fila Continuidad).
