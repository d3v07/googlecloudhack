import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Mirror tsconfig.json `paths` ("@/*": ["./*"]) so "@/lib/..." imports resolve
// under the dashboard root. tsx/ESM is handled by Vite's native transform.
export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL(".", import.meta.url)),
    },
  },
  test: {
    environment: "node",
    include: ["lib/**/*.test.ts"],
  },
});
