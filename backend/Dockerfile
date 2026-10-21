FROM python:3.11-slim

WORKDIR /app

# Install dependencies (Dockerfile must run inside /backend)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .
RUN ln -s /app /app/backend

# Remove .env if it exists
RUN rm -f .env .env.local .env.railway

# Writable folders, then drop root: the app never needs to run as root, so a bug in it
# can't be used to take over the container.
RUN mkdir -p static/uploads storage \
    && useradd --create-home --uid 10001 nimmi \
    && chown -R nimmi:nimmi /app
USER nimmi

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Start application
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
