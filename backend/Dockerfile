FROM python:3.11-slim

WORKDIR /app

# Install dependencies (Railway builds from repo root, so paths use backend/)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ .

# Create uploads directory
RUN mkdir -p static/uploads

# Expose port (Railway sets $PORT automatically)
ENV PORT=8000

CMD gunicorn -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT main:app
