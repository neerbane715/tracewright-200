import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",   // default 'localhost' resolves to ::1 on Windows
    port: 5174,          // 5173 stays free for the legacy console
    strictPort: true,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  build: { outDir: "dist", assetsInlineLimit: 0 },
});
