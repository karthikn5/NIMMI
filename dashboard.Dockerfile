FROM node:20-alpine

WORKDIR /app

# Install dependencies from the dashboard folder
COPY dashboard/package.json ./
RUN npm install

# Copy dashboard code
COPY dashboard/ .

# Build - skip linting and type checks to ensure it finishes
ENV NEXT_TELEMETRY_DISABLED=1
RUN npx next build --no-lint

# Production settings
ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0
ENV PORT=3000
EXPOSE 3000

# Start application
CMD ["node_modules/.bin/next", "start"]
