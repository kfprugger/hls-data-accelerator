import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiTarget = process.env.VITE_API_TARGET || "http://127.0.0.1:7071";

const apiProxy = {
  "/api": {
    target: apiTarget,
    changeOrigin: true,
  },
};

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: apiProxy,
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    proxy: apiProxy,
  },
});
