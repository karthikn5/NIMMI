FROM python:3.11-slim

WORKDIR /app

# Install dependencies (Railway builds from repo root, so paths use backend/)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ .

# Remove .env if it exists (Railway provides env vars - don't let local .env override)
RUN rm -f .env .env.local .env.railway

# Create uploads directory
RUN mkdir -p static/uploads

# Use single uvicorn process - lower memory than gunicorn+workers on Railway free tier
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
