# DocuMind AI — frontend

Next.js (App Router) + TypeScript + Tailwind + componentes de shadcn/ui + TanStack Query.
Convenciones y reglas: ver `CLAUDE.md` en la raíz.

## Requisitos

- Node 24 y pnpm 10 (`npm install -g --prefix ~/.local pnpm@10.34.9`, o `corepack enable`)
- La API corriendo en `http://127.0.0.1:8000` (`podman compose up -d`)

## Desarrollo

```bash
pnpm install
pnpm dev          # http://localhost:3000 — /api/* se reenvía a la API (next.config.ts)
```

Usá `localhost` y no `127.0.0.1`: es el origen (`APP_ORIGIN`) que la API acepta para renovar la sesión.

## Calidad

```bash
pnpm lint && pnpm typecheck && pnpm test && pnpm build
```

## Cómo habla con la API

- `src/lib/api/schema.ts` se genera desde `openapi.json` con `pnpm gen:api` (no editar a mano).
- `src/lib/api/client.ts`: cliente tipado (openapi-fetch). Los endpoints dentro de una organización
  reciben `params: inOrganization(id)`, que agrega el header `X-Organization-Id`.
- `src/lib/api/session.ts`: el access token vive solo en memoria; el refresh token es una cookie
  HttpOnly que este código nunca ve. Varios 401 a la vez comparten un único refresh (ADR 0004).
- Las reglas de roles de `src/lib/roles.ts` solo deciden qué botones mostrar: la API decide de verdad.
