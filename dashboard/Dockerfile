FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies
COPY package.json* dashboard/package.json* ./
RUN if [ -f package.json ]; then npm install; \
    elif [ -f dashboard/package.json ]; then cd dashboard && npm install; fi

# Copy app source and build
COPY . .

# Skip linting during build to avoid breaking on ESLint warnings
ENV NEXT_TELEMETRY_DISABLED=1
RUN if [ -d dashboard ]; then cd dashboard && npm run build -- --no-lint; \
    else npm run build -- --no-lint; fi

# Production runner
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0
ENV PORT=3000

# Copy built output (handles both relative and absolute paths)
COPY --from=builder /app/ .

EXPOSE 3000
CMD if [ -d dashboard ]; then cd dashboard && npm start; else npm start; fi
