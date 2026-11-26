import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// Automated accessibility scan (WCAG 2.1 A and AA rules that axe can check) on every page.
// Automated checks catch a subset of issues; keyboard and screen-reader behavior still need manual review.
const PAGES = ["/", "/decisions", "/studio", "/benchmark", "/data", "/history", "/methodology"];

for (const path of PAGES) {
  test(`no detectable WCAG A/AA violations on ${path}`, async ({ page }, info) => {
    // The desktop project also checks a tablet width, where some wide tables scroll sideways.
    if (info.project.name === "desktop" && process.env.A11Y_TABLET) await page.setViewportSize({ width: 820, height: 1180 });
    await page.goto(path);
    await expect(page.locator("main")).toBeVisible();
    await expect(page.locator(".skeleton")).toHaveCount(0, { timeout: 15_000 });
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
    const summary = results.violations.map((v) => `${v.id} (${v.impact}): ${v.nodes.length} node(s), e.g. ${v.nodes[0]?.target.join(" ")}`);
    expect(summary, summary.join("\n")).toEqual([]);
  });
}
