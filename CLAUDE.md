# CLAUDE.md

Claude Code instructions for Enterprise Decision Intelligence.

The shared, authoritative agent instructions live in `AGENTS.md`. Read it first; this file only adds Claude-specific notes so the two never drift apart.

## Session start

Follow the recovery protocol in `AGENTS.md` (reading order, git inspection, verification before resuming). The canonical specification is `MASTER_PROMPT.md`. Status lives in `PROGRESS.md`, `HANDOFF.md` and `TASKS.md`.

## Claude-specific notes

- Prefer small, verifiable increments. Run `pytest -q` and `npm test` after changes to engine code; parity fixtures break loudly when Python and TypeScript evaluators diverge.
- Regenerate web artifacts with `edi export-web` after any change to the benchmark, forecasting or evaluator. Commit the resulting JSON only if it stays small (the build check fails above the size budget in `apps/web/scripts/check-size.mjs`).
- Use Playwright screenshots for UI review (`npm run screenshots`), and look at them before calling a UI change done.
- Write in plain, professional language. No em dashes in user-facing copy, no marketing superlatives, no claims of enterprise adoption.
- Update `PROGRESS.md` and `HANDOFF.md` before context compaction when practical and always before ending a session.
