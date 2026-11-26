import { test } from "@playwright/test";

const PAGES = [
  ["overview", "/"],
  ["workspace", "/decisions"],
  ["studio", "/studio"],
  ["benchmark", "/benchmark"],
  ["data", "/data"],
  ["history", "/history"],
  ["methodology", "/methodology"],
] as const;
const SIZES = [
  ["desktop", 1440, 900],
  ["tablet", 820, 1180],
  ["mobile", 390, 844],
] as const;

test.describe.configure({ mode: "serial" });

for (const [name, path] of PAGES) {
  for (const [size, w, h] of SIZES) {
    test(`${name} at ${size}`, async ({ page }, info) => {
      test.skip(info.project.name !== "desktop", "screenshots use explicit viewports");
      await page.setViewportSize({ width: w, height: h });
      await page.goto(path);
      await page.waitForLoadState("networkidle");
      await page.locator(".skeleton").first().waitFor({ state: "detached", timeout: 15_000 }).catch(() => undefined);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      if (overflow > 1) console.warn(`horizontal overflow ${overflow}px on ${name} at ${size}`);
      await page.screenshot({ path: `../../docs/screenshots/${name}-${size}.png`, fullPage: true });
    });
  }
}
