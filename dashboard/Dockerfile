FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies (Railway builds from repo root, no lockfile = correct Linux binaries)
COPY dashboard/package.json ./
RUN npm install --include=optional

# Copy app source and build
COPY dashboard/ .

# Remove .env files so Railway env vars take effect
RUN rm -f .env .env.local

RUN npm run build

# Production runner - use next start (simpler than standalone server.js)
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0

# Copy built output
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./

EXPOSE 3000
CMD ["npm", "start"]
