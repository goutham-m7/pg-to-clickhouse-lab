import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:58239",
    channel: process.env.CHROME_CHANNEL || undefined,
  },
  webServer: {
    command:
      "cd .. && uv run --locked --offline python -m ledger.serve --port 58239",
    url: "http://127.0.0.1:58239",
  },
});
