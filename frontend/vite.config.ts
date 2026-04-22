import path from "node:path"
import { fileURLToPath } from "node:url"

import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import { defineConfig } from "vitest/config"

const srcPath = fileURLToPath(new URL("./src", import.meta.url))

const backendUrl = process.env.VITE_BACKEND_URL || "http://localhost:8002"

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(srcPath),
    },
  },
  server: {
    proxy: {
      "/api": {
        target: backendUrl,
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq) => {
            proxyReq.setHeader("Host", "localhost:8002")
          })
        },
      },
      "/accounts": {
        target: backendUrl,
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq) => {
            proxyReq.setHeader("Host", "localhost:8002")
          })
        },
      },
    },
  },
  build: {
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (
            id.includes("react-markdown") ||
            id.includes("remark-gfm") ||
            id.includes("js-yaml") ||
            id.includes("/diff/")
          ) {
            return "editor"
          }

          if (id.includes("/recharts/")) {
            return "charts"
          }

          if (
            id.includes("/lucide-react/") ||
            id.includes("/sonner/") ||
            id.includes("/next-themes/")
          ) {
            return "ui"
          }

          if (
            id.includes("/react/") ||
            id.includes("/react-dom/") ||
            id.includes("/react-router-dom/") ||
            id.includes("/@tanstack/react-query/")
          ) {
            return "framework"
          }
        },
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/test-setup.ts",
  },
})
