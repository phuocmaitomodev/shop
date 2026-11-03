import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5176,
    strictPort: true,
  },
  test: {
    environment: 'jsdom',
    env: {
      VITE_API_BASE_URL: 'http://localhost:8000/api/v1',
    },
  },
})
