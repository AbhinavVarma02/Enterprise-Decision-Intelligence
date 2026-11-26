import { expect, test } from "@playwright/test";

test.describe("signature decision journey", () => {
  test("overview to decision, change an assumption, approve, see it in history", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

    await page.goto("/");
    await expect(page.getByText(/proposed replenishment orders need a decision/)).toBeVisible();
    const rows = page.locator("table.data tbody tr");
    await expect(rows.first()).toBeVisible();
    await page.getByRole("link", { name: "Review the top decision" }).click();

    await expect(page).toHaveURL(/\/decisions\/case-/);
    await expect(page.locator("#verdict-h")).toBeVisible();
    await expect(page.getByRole("list", { name: "Validation gates" }).locator("li")).toHaveCount(7);
    await page.getByRole("button", { name: "Wait one day, then order" }).click();
    await expect(page.getByRole("heading", { name: /Wait one day, then order:/ })).toBeVisible();

    await page.getByRole("link", { name: /scenario studio/ }).click();
    await expect(page).toHaveURL(/\/studio\/case-/);
    const before = await page.getByTestId("studio-recommended").innerText();
    await page.getByRole("button", { name: "+2 days" }).click();
    await page.locator("#s-demand").fill("0.4");
    await expect(page).toHaveURL(/primary_delay_days=2/);
    await expect.poll(async () => page.getByTestId("studio-recommended").innerText()).not.toBe(before);
    await page.getByRole("button", { name: "Save scenario" }).click();
    await expect(page.getByRole("button", { name: "Saved to history" })).toBeVisible();

    await page.goBack();
    await page.goto("/decisions");
    await page.getByRole("button", { name: "Escalate", exact: true }).click();
    await expect(page.getByRole("status").filter({ hasText: "Recorded: escalated" })).toBeVisible();

    await page.getByRole("link", { name: "decision history", exact: true }).click();
    await expect(page.getByText(/recorded decisions/)).toBeVisible();
    await expect(page.getByText("Hash chain: Intact")).toBeVisible();
    await expect(page.locator("table.data tbody tr")).toHaveCount(2);
    expect(errors, errors.join("\n")).toEqual([]);
  });

  test("every page renders without console errors and has one h1 or verdict", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    for (const path of ["/", "/decisions", "/studio", "/benchmark", "/data", "/history", "/methodology", "/nowhere"]) {
      await page.goto(path);
      await expect(page.locator("main")).toBeVisible();
      await expect(page.locator(".skeleton")).toHaveCount(0, { timeout: 15_000 });
    }
    expect(errors).toEqual([]);
  });

  test("benchmark condition switch and keyboard navigation", async ({ page }) => {
    await page.goto("/benchmark");
    await page.getByRole("button", { name: "Normal operations" }).click();
    await expect(page.getByRole("button", { name: "Normal operations" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByText("Hypotheses and verdicts")).toBeVisible();
    await page.goto("/");
    await expect(page.locator("main h1, main h2").first()).toBeVisible();
    await page.keyboard.press("Tab");
    await expect(page.getByText("Skip to content")).toBeFocused();
  });

  test("history import rejects a malformed file", async ({ page }) => {
    await page.goto("/history");
    const [chooser] = await Promise.all([page.waitForEvent("filechooser"), page.getByRole("button", { name: "Import log" }).click()]);
    await chooser.setFiles({ name: "bad.json", mimeType: "application/json", buffer: Buffer.from('{"format":"nope"}') });
    await expect(page.getByText(/does not match the decision-log format/)).toBeVisible();
  });

  test("an imported decision bundle is validated in the browser", async ({ page, request }) => {
    const bundle = await (await request.get("/data/example_bundle.json")).body();
    await page.goto("/history");
    const [chooser] = await Promise.all([page.waitForEvent("filechooser"), page.getByRole("button", { name: "Choose a bundle file" }).click()]);
    await chooser.setFiles({ name: "bundle.json", mimeType: "application/json", buffer: bundle });
    await expect(page.locator(".chip").filter({ hasText: /Reject|Recommend|Escalate|Defer|Investigate/ }).last()).toBeVisible();
  });
});
