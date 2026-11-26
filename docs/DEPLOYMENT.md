# Deployment

The product is a static site. Hosting it costs nothing on Cloudflare Pages' free plan, needs no server code, and needs no secrets in the repository.

**Status: not deployed.** The build environment used to create this project had no Cloudflare credentials, and none were requested. No URL exists yet. The steps below are what the owner runs once, from their own machine, signed in to their own Cloudflare account.

## Prerequisites

- Node.js 20 or newer.
- A Cloudflare account (free plan is enough). No payment method is required for Pages.
- The site built locally: `cd apps/web && npm ci && npm run build`. The build fails if the output breaks the size budget or contains a `functions/` directory.

## One-time setup

From the repository root:

```bash
npx wrangler login                     # opens a browser; signs in to YOUR account
npx wrangler whoami                    # confirm the account before creating anything
npx wrangler pages project create enterprise-decision-intelligence --production-branch main
```

Use a new project with this exact name. Do not reuse or overwrite an existing Pages project.

## Deploy

```bash
cd apps/web
npm ci
npm run build
npx wrangler pages deploy dist --project-name enterprise-decision-intelligence --branch main
```

Wrangler prints the deployment URL. The production address will be `https://enterprise-decision-intelligence.pages.dev` if that subdomain is free; Cloudflare appends a suffix when it is taken, so use the URL wrangler prints.

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
cd apps/web && BASE_URL="$URL" npx playwright test e2e/journey.spec.ts --project=desktop
```

`playwright.config.ts` reads `BASE_URL`; without it the tests start `vite preview` locally.

## Updating results

The site only shows what is in `apps/web/public/data/`. To publish new results, rerun the pipeline and export, then rebuild and deploy:

```bash
edi run-all --config configs/research.yaml
edi export-web --config configs/research.yaml
cd apps/web && npm run build && npx wrangler pages deploy dist --project-name enterprise-decision-intelligence --branch main
```

## Rollback

Every deploy is kept. In the Cloudflare dashboard, open the project's Deployments tab and choose "Rollback" on an earlier deployment, or redeploy an earlier commit's `dist/`.

## Other static hosts

Any static host works (GitHub Pages, Netlify, an S3 bucket behind a CDN). Two things need manual equivalents: the security headers in `_headers`, and serving `index.html` for unknown paths.
