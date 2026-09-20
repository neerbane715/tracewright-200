import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({
  base: process.env.VITE_BASE || '/',
  plugins: [react()],
    // Bind IPv4 explicitly: the default 'localhost' resolves to ::1 on Windows,
  // which some tools and browsers on a demo machine will not reach.
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
