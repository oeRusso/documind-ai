# Etapa 3 — Primer deploy y CI/CD

- **Fase:** A — Fundamentos (cierra con el tag `v0.1.0`)
- **Duración estimada:** 3 a 4 días
- **Rama:** `development` (PR a `main` al cerrar la etapa)
- **Estado:** pendiente

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

## Referencias

- Parte 1: §2 (arquitectura), §7 (red, secretos, continuidad), §8 (CI, paso 5).
- Parte 2: "Servicios gratuitos de terceros".
