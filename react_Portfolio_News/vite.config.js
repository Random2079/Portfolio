import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Vanilla API: Portfolio_News → python -m portfolio_news serve → :8765
// Production build is served by that API at /app/ (see Portfolio_News MAP §7R).
export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === "build" ? "/app/" : "/",
  server: {
    // Windows: default can bind [::1] only → 127.0.0.1:5173 dead
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
      },
    },
  },
}));
