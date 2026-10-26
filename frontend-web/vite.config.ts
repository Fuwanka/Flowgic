import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Один origin в dev и Docker: браузер не хранит адрес внутреннего backend и не требует CORS.
const proxy = {
  "/api": {
    target: process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000",
    changeOrigin: true,
  },
};
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, proxy },
  preview: { port: 4173, strictPort: true, proxy },
  build: { chunkSizeWarningLimit: 850 },
  test: {
    include: ["src/**/*.test.ts"],
    environment: "node",
    restoreMocks: true,
  },
});
