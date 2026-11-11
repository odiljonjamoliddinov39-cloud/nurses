import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In Docker Compose set VITE_PROXY_TARGET=http://backend:8000 (localhost is the container itself).
const target = process.env.VITE_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": { target, rewrite: (p) => p.replace(/^\/api/, "") } } },
});
