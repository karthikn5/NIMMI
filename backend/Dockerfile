FROM python:3.11-slim

WORKDIR /app

# Install dependencies (Dockerfile must run inside /backend)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Remove .env if it exists
RUN rm -f .env .env.local .env.railway

# Create uploads directory
RUN mkdir -p static/uploads

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Start application
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
