// Fails the build when the static site exceeds the project's budget (well below Cloudflare Pages limits:
// 20,000 files and 25 MiB per file on the Free plan).
import { readdirSync, statSync, existsSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const DIST = fileURLToPath(new URL("../dist/", import.meta.url));
const LIMITS = { totalBytes: 3_000_000, fileBytes: 1_000_000, files: 100 };

function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

if (existsSync(join(DIST, "functions"))) {
  console.error("dist/functions exists: server-side code is not allowed (ADR-0003)");
  process.exit(1);
}
const files = walk(DIST);
const sizes = files.map((f) => [f.replace(DIST, ""), statSync(f).size]);
const total = sizes.reduce((s, [, b]) => s + b, 0);
const big = sizes.filter(([, b]) => b > LIMITS.fileBytes);
console.log(`site: ${files.length} files, ${(total / 1e6).toFixed(2)} MB`);
for (const [f, b] of sizes.sort((a, b) => b[1] - a[1]).slice(0, 6)) console.log(`  ${(b / 1e3).toFixed(1)} kB  ${f}`);
if (files.length > LIMITS.files || total > LIMITS.totalBytes || big.length) {
  console.error("size budget exceeded", { files: files.length, total, big });
  process.exit(1);
}
