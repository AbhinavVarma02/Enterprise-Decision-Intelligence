# ADR-0003: No Pages Functions or Workers

Status: accepted (2026-11-25)

Context. Cloudflare offers Functions and Workers with free quotas, but quotas and billing rules change and add an operational surface.

Decision. Static assets only. Security headers via `_headers`.

Reasons. A hard zero-cost guarantee and nothing to secure server-side.

Trade-offs. No shared state between visitors; decision records stay in each browser.

Validation. `apps/web/dist` contains no `functions/` directory; the build check fails if one appears.
