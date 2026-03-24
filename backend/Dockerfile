FROM python:3.11-slim

WORKDIR /app

# Install dependencies
# This handles build from root (backend/requirements.txt) or from /backend (requirements.txt)
COPY requirements.txt* backend/requirements.txt* ./
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; \
    elif [ -f backend/requirements.txt ]; then pip install --no-cache-dir -r backend/requirements.txt; fi

# Copy application code
COPY . .

# Remove .env if it exists
RUN rm -f .env .env.local .env.railway

# Create uploads directory
RUN mkdir -p static/uploads

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Start application
# If we are in /app and main.py is there, run it. If it's in backend/main.py, run that.
CMD if [ -f main.py ]; then uvicorn main:app --host 0.0.0.0 --port $PORT; \
    else cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT; fi
