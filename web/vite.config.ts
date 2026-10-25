import { defineConfig } from 'vite'
import { resolve } from 'path'

export default defineConfig({
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    // Vite >= 6.4.4 enforces fs.allow on `?raw` imports in tests too. Setting it
    // replaces the default (project root), so list the root and the one extra
    // directory the tests import from (the served FTL bundle).
    fs: { allow: [resolve(__dirname), resolve(__dirname, '../strings')] },
    proxy: {
      '/thesaurus': 'http://localhost:8080',
      '/forge': 'http://localhost:8080',
      '/health': 'http://localhost:8080',
      '/strings': 'http://localhost:8080',
    },
  },
  test: {
    environment: 'happy-dom',
    include: ['src/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'text-summary', 'html'],
      reportsDirectory: 'coverage',
      include: ['src/**/*.ts'],
      exclude: ['src/**/*.test.ts', 'src/**/*.d.ts'],
    },
  },
})
