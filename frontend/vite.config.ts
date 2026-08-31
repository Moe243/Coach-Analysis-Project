import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: 4173,
      proxy: env.VITE_API_PROXY_TARGET
        ? {
            "/api": {
              target: env.VITE_API_PROXY_TARGET,
              changeOrigin: true,
              rewrite: (path) => path.replace(/^\/api/, ""),
            },
          }
        : undefined,
    },
    preview: { host: "127.0.0.1", port: 4173 },
    test: {
      environment: "jsdom",
      globals: true,
      include: ["src/**/*.test.{ts,tsx}"],
      setupFiles: "./src/test/setup.ts",
      css: true,
      clearMocks: true,
    },
  };
});
