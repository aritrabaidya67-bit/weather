import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

/**
 * The dev server proxies /api to the FastAPI backend so the browser can use
 * same-origin URLs (no CORS juggling) while the frontend still supports talking
 * to a remote backend through VITE_API_BASE_URL.
 */
export default defineConfig(({ mode }) => {
  // Resolve env files relative to this config file (avoids needing @types/node).
  const env = loadEnv(mode, ".", "");
  const target = env.VITE_PROXY_TARGET || "http://127.0.0.1:8000";
  const port = Number(env.VITE_DEV_PORT || 5173);

  return {
    plugins: [react(), tailwindcss()],
    server: {
      host: true,
      port,
      strictPort: false,
      proxy: {
        "/api": {
          target,
          changeOrigin: true,
          ws: true,
        },
      },
    },
    build: {
      outDir: "dist",
      sourcemap: false,
      chunkSizeWarningLimit: 1200,
    },
  };
});
