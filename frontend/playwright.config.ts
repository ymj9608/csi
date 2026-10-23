import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  use: {
    baseURL: process.env.CSI_E2E_BASE_URL || "http://127.0.0.1:5174",
    channel: "chrome",
    viewport: { width: 1440, height: 1000 },
  },
  reporter: "list",
  outputDir: "../.runtime/playwright",
});
