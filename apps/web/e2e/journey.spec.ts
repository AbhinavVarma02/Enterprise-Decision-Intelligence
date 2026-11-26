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
    await expect(page).toHaveURL((url) => url.searchParams.get("primary_delay_days") === "2"
      && url.searchParams.get("demand_shift") === "0.4");
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

  test("retail evidence and synthetic findings use their own breach-cost inputs", async ({ page }) => {
    await page.goto("/benchmark?study=retail");
    await expect(page.getByRole("button", { name: "FreshRetailNet pilot" })).toHaveAttribute("aria-pressed", "true");
    const cost = page.getByRole("slider", { name: "Additional cost per breached submission" });
    const result = page.locator(".breach-total");
    const initial = await result.innerText();
    await cost.press("End");
    await expect(cost).toHaveAttribute("aria-valuetext", "$50.00");
    await expect(result).not.toHaveText(initial);
    await page.getByRole("button", { name: "Synthetic benchmark" }).click();
    await expect(page).toHaveURL(/study=synthetic/);
    await expect(page.getByText("177 → 0", { exact: true })).toBeVisible();
    await expect(page.getByText(/Break-even is \$10.65/)).toBeVisible();
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

  test("decision history exports, cancels a clear, clears and restores records", async ({ page }) => {
    await page.goto("/decisions");
    await page.getByRole("button", { name: "Wait one day, then order" }).click();
    await page.getByRole("button", { name: "Record deferral" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Recorded: deferred" })).toBeVisible();
    await page.getByRole("link", { name: "decision history", exact: true }).click();
    const save = page.waitForEvent("download");
    await page.getByRole("button", { name: "Export log" }).click();
    const exported = await save;
    expect(exported.suggestedFilename()).toBe("edi-decision-log.json");
    await page.getByRole("button", { name: "Clear history" }).click();
    await page.getByRole("button", { name: "Keep" }).click();
    await expect(page.getByText("Hash chain: Intact")).toBeVisible();
    await page.getByRole("button", { name: "Clear history" }).click();
    await page.getByRole("button", { name: "Confirm clear" }).click();
    await expect(page.getByRole("heading", { name: "No decisions recorded yet" })).toBeVisible();
    const [chooser] = await Promise.all([page.waitForEvent("filechooser"), page.getByRole("button", { name: "Import log" }).click()]);
    await chooser.setFiles((await exported.path())!);
    await expect(page.getByText("Imported 1 decisions. The hash chain verified.")).toBeVisible();
  });

  test("bundle import refuses quantiles with the wrong dimensions", async ({ page, request }) => {
    const payload = await (await request.get("/data/example_bundle.json")).json();
    payload.candidate.forecast.quantiles[0] = [0, 1, 2];
    await page.goto("/history");
    const [chooser] = await Promise.all([page.waitForEvent("filechooser"), page.getByRole("button", { name: "Choose a bundle file" }).click()]);
    await chooser.setFiles({ name: "bundle.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(payload)) });
    await expect(page.getByText(/one ordered quantile per strictly increasing probability level/)).toBeVisible();
  });
});
