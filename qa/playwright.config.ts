import { defineConfig, devices } from '@playwright/test'

const frontendPort = process.env.QA_FRONTEND_PORT ?? '4173'
const baseURL = process.env.QA_BASE_URL ?? `http://127.0.0.1:${frontendPort}`

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [['line'], ['html', { open: 'never' }]] : 'line',
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium-desktop',
      use: { ...devices['Desktop Chrome'], channel: 'chrome', viewport: { width: 1366, height: 768 } },
    },
    {
      name: 'chromium-mobile',
      use: { ...devices['Pixel 5'], channel: 'chrome', viewport: { width: 390, height: 844 } },
    },
  ],
  webServer: process.env.QA_BASE_URL
    ? undefined
    : {
        command: `npm --prefix ../frontend run preview -- --host 127.0.0.1 --port ${frontendPort}`,
        url: baseURL,
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
      },
})
