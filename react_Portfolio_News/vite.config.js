import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Vanilla API lives in Portfolio_News: python -m portfolio_news serve → :8765
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
      },
    },
  },
});
