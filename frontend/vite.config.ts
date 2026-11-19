import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// in dev, the api runs separately on :8000
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://localhost:8000' } },
})
