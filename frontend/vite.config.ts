import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // The backend owns every provider call; the browser only ever talks to /api.
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    target: "es2022",
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    css: false,
    // Playwright owns e2e/; vitest must not try to run those specs as unit tests.
    exclude: ["**/node_modules/**", "**/dist/**", "e2e/**"],
  },
});
