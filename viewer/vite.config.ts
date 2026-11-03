import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { DEFAULT_API_PORT, HOST } from "./server/config.ts";

const apiPort = Number(process.env.VIEWER_API_PORT ?? DEFAULT_API_PORT);

export default defineConfig({
  plugins: [react()],
  server: {
    host: HOST, // 127.0.0.1 only, like the API
    port: Number(process.env.VIEWER_WEB_PORT ?? 5174),
    strictPort: true,
    proxy: {
      "/api": { target: `http://${HOST}:${apiPort}`, changeOrigin: true },
    },
  },
});
