/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  // OPTISERVE_BACKEND in frontend/.env.local overrides where /api is forwarded during development.
  const backend = loadEnv(mode, ".", "OPTISERVE_").OPTISERVE_BACKEND ?? "http://localhost:8000";
  const proxy = { "/api": { target: backend, changeOrigin: true } };
  return {
    plugins: [react(), tailwindcss()],
    server: { port: 5173, proxy },
    preview: { proxy },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      css: false,
      restoreMocks: true,
    },
  };
});
