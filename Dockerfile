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

# Pre-cache Hugging Face FLAN-T5 model weights at build time
ENV HF_HOME=/app/hf_cache
RUN python -c "from transformers import AutoTokenizer, AutoModelForSeq2SeqLM; \
    AutoTokenizer.from_pretrained('rayenthabet004/tt-multi-engine-t5'); \
    AutoModelForSeq2SeqLM.from_pretrained('rayenthabet004/tt-multi-engine-t5', low_cpu_mem_usage=True)"

# Force offline mode at runtime so from_pretrained() never touches the
# network or writes cache-validation files (defense in depth against any
# file-watcher or cache-lock issues)
ENV HF_HUB_OFFLINE=1

# Copy application source code and data
COPY . .

# Expose default port
EXPOSE 8000

ENV PORT=8000
ENV PYTHONUNBUFFERED=1

# Start FastAPI server
CMD ["python", "web_app.py"]
