FROM node:20-alpine

WORKDIR /app

# Install all dependencies (including dev for build)
COPY package.json ./
RUN npm install

# Copy app source
COPY . .

# Build - skip linting to avoid breaking on warnings
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build -- --no-lint

# Production settings
ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0
ENV PORT=3000
EXPOSE 3000

# Start application using absolute path to next to bypass npm path issues
CMD ["./node_modules/.bin/next", "start"]
