import { defineConfig } from '@playwright/test'

// e2e config for the DOM label layer suite. The dev server serves the Vite
// module graph, so the fixture pages can import /src directly. reuseExistingServer
// keeps local iteration cheap; CI spins a fresh one.
export default defineConfig({
  testDir: './e2e',
  timeout: 30000,
  use: { baseURL: 'http://localhost:5173' },
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
    timeout: 60000,
  },
})
