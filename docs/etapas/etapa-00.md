# Etapa 0 — Preparación y prueba de humo del VPS

- **Fase:** A — Fundamentos
- **Duración estimada:** 2 a 3 días
- **Rama:** `development` (PR a `main` al cerrar la etapa)
- **Estado:** en curso

## Objetivo

Eliminar el mayor riesgo del proyecto (que el VPS no aguante un LLM) antes de escribir una línea de la app.

## Tareas

- [ ] Endurecer el VPS: usuario sin root con sudo, SSH solo con llave, login por contraseña deshabilitado, firewall que solo permita SSH, actualizaciones automáticas de seguridad.
- [ ] Crear swap de 4 GB si el VPS tiene 8 GB de RAM: evita que el sistema mate procesos en picos.
- [ ] Revisar el plan real del VPS (`free -h`, `nproc`, `df -h`) y compararlo con la tabla de dimensionamiento de la Parte 2.
- [ ] Instalar Podman, `podman-compose` y `cloudflared`.
- [ ] Prueba de humo de IA: levantar Ollama en un contenedor, bajar 2 o 3 modelos candidatos y medir RAM, tokens por segundo y calidad con 5 preguntas en español.
- [ ] Preparar el entorno local: Python 3.12 con uv, Node LTS con pnpm, Podman Desktop.
- [x] Crear el repo con la estructura de carpetas, `CLAUDE.md`, `.gitignore`, `.env.example` y licencia (AGPL-3.0, coherente con PyMuPDF).
- [x] Publicar el repo en GitHub (público: Actions y GHCR gratis): https://github.com/oeRusso/documind-ai
- [ ] Escribir `docs/decisions/0001-vps-y-modelo.md` con los resultados de la prueba de humo.

## Fuera de alcance

- Cualquier código de la aplicación (backend, frontend, compose). Arranca en la etapa 1.
- Elegir el modelo definitivo: los candidatos se evalúan contra el dataset en las etapas 6 y 7. Acá solo se descarta lo que no entra en el VPS.
- Cloudflare Tunnel configurado y en uso (etapa 3); acá solo se instala `cloudflared`.
- pre-commit y detect-secrets: necesitan el proyecto Python, entran en la etapa 1.

## Criterios de terminado

- [ ] El VPS solo acepta SSH con llave y no tiene otros puertos abiertos.
- [ ] `docs/decisions/0001-vps-y-modelo.md` registra la RAM disponible, los modelos probados y sus tokens por segundo.
- [ ] El repo existe en GitHub con `CLAUDE.md` y los archivos de etapas.

## Notas

- Candidatos para la prueba de humo: familia Qwen pequeña (3 a 4B), Gemma pequeña, Phi-4 Mini y Granite, en Q4. Criterios: calidad en español, licencia, RAM y tokens por segundo.
- **RX 6600 en local**: la RX 6600 (gfx1032) no está en la lista oficial de ROCm. Con la imagen `ollama/ollama:rocm` suele hacer falta `HSA_OVERRIDE_GFX_VERSION=10.3.0` y pasar `/dev/kfd` y `/dev/dri` al contenedor de Podman. La otra opción es el backend Vulkan de Ollama. No bloquea la etapa: el VPS es lo que importa.
- La tabla de seguridad de la Parte 1 (§7) ubica detect-secrets en la etapa 0, pero la Parte 2 pone pre-commit en la etapa 1. Se resuelve en la etapa 1.
- Los diagramas de los planes no se exportaron (quedaron como `[embedded content: …]`). Conviene rehacerlos en Mermaid; a más tardar en la etapa 12.

## Referencias

- Parte 2: "Dimensionar el VPS antes de elegir modelos", "Cómo trabajar con Claude Code".
- Parte 1: §7 (fila Secretos).
