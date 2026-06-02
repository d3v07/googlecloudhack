import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Emit a self-contained server bundle (.next/standalone) so the Docker image
  // ships only the traced runtime deps — no full node_modules. Required for the
  // slim Cloud Run image (#32).
  output: "standalone",
};

export default nextConfig;
