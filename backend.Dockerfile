FROM python:3.11-slim

WORKDIR /app

# Install dependencies from the backend folder
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ .

# Remove .env if it exists
RUN rm -f .env .env.local .env.railway

# Create uploads directory
RUN mkdir -p static/uploads

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Start application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
