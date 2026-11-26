import { defineConfig, devices } from "@playwright/test";

const chrome = process.env.CHROME_PATH;
// Set BASE_URL to test a deployed site; otherwise a local `vite preview` is started.
const remote = process.env.BASE_URL;

export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: remote ?? "http://127.0.0.1:4173",
    trace: "off",
    launchOptions: chrome ? { executablePath: chrome } : {},
  },
  webServer: remote
    ? undefined
    : {
        command: "npm run preview",
        url: "http://127.0.0.1:4173",
        reuseExistingServer: true,
        timeout: 60_000,
      },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
});
