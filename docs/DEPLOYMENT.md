# Deployment

The product is a static site. Hosting it costs nothing on Cloudflare Pages' free plan, needs no server code, and needs no secrets in the repository.

The release uses the dedicated `enterprise-decision-intelligence` Pages project. The commands below reproduce the static deployment from an authorized Wrangler session.

The production deployment was verified on 2026-11-26. It serves the build from source commit `6638da5ce64f5567d5c7358a3a0c91ec52d55248`. [Production](https://enterprise-decision-intelligence.pages.dev/) · [Immutable deployment](https://3db57a48.enterprise-decision-intelligence.pages.dev/)

## Prerequisites

- Node.js 22 or newer.
- A Cloudflare account (free plan is enough). No payment method is required for Pages.
- The site built locally: `cd apps/web && npm ci && npm run build`. The build fails if the output breaks the size budget or contains a `functions/` directory.

## One-time setup

From the repository root:

```bash
npx wrangler login                     # opens a browser; signs in to YOUR account
npx wrangler whoami                    # confirm the account before creating anything
npx wrangler pages project create enterprise-decision-intelligence --production-branch main --force
```

For first creation with Wrangler 4.168, the create flag selects direct Pages hosting. The audit already created this project. Subsequent deployments use the existing project and the standard deploy command.

## Deploy

```bash
cd apps/web
npm ci
npm run build
npx wrangler pages deploy dist --project-name enterprise-decision-intelligence --branch main
```

Wrangler prints a deployment-specific URL. The project's production domain is `https://enterprise-decision-intelligence.pages.dev`.

## What gets served

- `dist/index.html` and hashed assets under `dist/assets/` (cached for a year, immutable).
- `dist/data/*.json`: precomputed results (cached for five minutes).
- `dist/_headers`: Content-Security-Policy and other security headers (see `docs/SECURITY.md`).
- There is no `404.html`, so Pages serves `index.html` for unknown paths and the app's router shows its own "page not found" view. Deep links such as `/decisions/case-...` therefore work on reload.

## Verify after deploying

```bash
URL=https://enterprise-decision-intelligence.pages.dev   # or the URL wrangler printed
curl -sI "$URL/" | grep -i -E "content-security-policy|x-content-type-options"
curl -s "$URL/data/meta.json" | head -c 300
cd apps/web && BASE_URL="$URL" npx playwright test e2e/journey.spec.ts e2e/a11y.spec.ts
BASE_URL="$URL" A11Y_TABLET=1 npx playwright test e2e/a11y.spec.ts --project=desktop
```

`playwright.config.ts` reads `BASE_URL`; without it the tests start `vite preview` locally.

## Updating results

The site only shows what is in `apps/web/public/data/`. To publish new results, rerun the pipeline and export, then rebuild and deploy:

```bash
edi run-all --config configs/research-real.yaml
edi selective-validation --config configs/research-real.yaml
edi export-web --config configs/research-real.yaml
cd apps/web && npm run build && npx wrangler pages deploy dist --project-name enterprise-decision-intelligence --branch main
```

## Rollback

Every deploy is kept. In the Cloudflare dashboard, open the project's Deployments tab and choose "Rollback" on an earlier deployment, or redeploy an earlier commit's `dist/`.

## Other static hosts

Any static host works (GitHub Pages, Netlify, an S3 bucket behind a CDN). Two things need manual equivalents: the security headers in `_headers`, and serving `index.html` for unknown paths.
