FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies (Railway builds from repo root)
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci

# Copy app and build
COPY dashboard/ .
RUN npm run build

# Production runner
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
