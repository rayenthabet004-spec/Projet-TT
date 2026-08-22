FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code and data
COPY . .

# Expose default port
EXPOSE 8000

ENV PORT=8000
ENV PYTHONUNBUFFERED=1

# Start FastAPI server
CMD ["python", "web_app.py"]
