# 0005 — Sin Cloudflare Turnstile: campo trampa y límite de intentos

- **Estado:** aceptada
- **Fecha:** 2026-11-06
- **Etapa:** 02

## Contexto

La Parte 1 (§7) pone Cloudflare Turnstile en el registro para frenar bots. Después se sumó una regla
a `CLAUDE.md`: no usar servicios de terceros ni APIs externas sin permiso y no crear recursos en
Cloudflare más allá de DNS. Turnstile es gratuito, pero es una API externa y requiere crear un widget
en Cloudflare. Esteban decidió no usarlo: solo lo que ya está disponible, sin servicios nuevos.

## Opciones consideradas

1. **Turnstile**: muy efectivo contra bots, gratis, pero depende de Cloudflare y de una llamada
   externa en cada registro.
2. **Campo trampa (honeypot) + límite de intentos**: todo dentro de la app. Frena bots simples y
   ataques de fuerza bruta; no frena a un bot que ejecute JavaScript y se comporte como una persona.
3. **CAPTCHA propio** (imagen o pregunta): sin dependencias, pero molesto para las personas y fácil de
   resolver con OCR.

## Decisión

Opción 2:

- El formulario de registro tiene un campo invisible para personas. Si llega con contenido, la API
  responde como si el registro hubiera fallado por datos inválidos, sin dar pistas.
- El límite de intentos por IP (y por email en el login) del paso 20 cubre registro, login y
  aceptación de invitaciones.

## Consecuencias

- No hay variables `TURNSTILE_*` ni llamadas a servicios externos.
- La protección es más débil contra bots sofisticados. Para un proyecto de portfolio con poco tráfico
  es aceptable. Si aparecen registros automatizados, revisar esta decisión (y pedir permiso para
  Turnstile u otra opción).
- La etapa 12 (demo pública) también queda sin Turnstile: usa límites de uso más estrictos.

## Evidencia

Decisión de Esteban del 2026-11-06. No hay métricas: no hubo tráfico real todavía.
Implementación y tests: `backend/tests/integration/test_rate_limits_api.py` (límites) y
`test_auth_api.py` (campo trampa).
