# Multi-stage build for the Next.js dashboard → Cloud Run (#32).
# Produces a slim image from Next's standalone output (no full node_modules).

# ── deps ────────────────────────────────────────────────────────────────────
FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ── build ───────────────────────────────────────────────────────────────────
FROM node:22-slim AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Reads/writes are configured at runtime via env; build only needs to compile.
RUN npm run build

# ── runtime ─────────────────────────────────────────────────────────────────
FROM node:22-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production
# Cloud Run injects PORT; Next standalone server honors it.
ENV PORT=8080

# Non-root user for container security.
RUN useradd --no-create-home --shell /bin/false nextjs

# Standalone server + its traced node_modules, plus static assets and public/.
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public

USER nextjs
EXPOSE 8080

# server.js is emitted by Next's standalone output at the app root.
CMD ["node", "server.js"]
