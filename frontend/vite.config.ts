/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The app calls the API on its own origin (/api/v1/...). In development Vite forwards those
// requests to the backend; in production Vercel does the same (vercel.json). Same origin lets
// the refresh token stay in a Strict, HttpOnly cookie.
// (Read via globalThis so browser code doesn't get Node's types.)
const env = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env;
const backend = env?.MENTORX_BACKEND_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { "/api": { target: backend, changeOrigin: false } },
  },
  preview: {
    proxy: { "/api": { target: backend, changeOrigin: false } },
  },
  build: {
    sourcemap: true,
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
