FROM python:3.11-slim

WORKDIR /app

# Install system dependencies if any (usually none needed for basic python)
# RUN apt-get update && apt-get install -y --no-install-recommends ...

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port (default fastapi port often 8000)
EXPOSE 8000

# Run application
# Host 0.0.0.0 is required for Docker networking
# Environment variables must be passed at runtime using -e or Kubernetes env
# Environment variables with defaults (can be overridden at runtime)
ENV OLLAMA_BASE_URL="http://localhost:11434"
ENV OLLAMA_MODEL="qwen3.5:2b"
ENV OLLAMA_TIMEOUT="180"
ENV MEMORY_API_URL="http://localhost:3000"
ENV CHATBOT_API_URL="http://localhost:3000"
ENV AGENT_API_URL="http://localhost:3000"
# Admin API URL for LLM assignment config resolution (GAP 6)
ENV ADMIN_API_URL=""
ENV DEBUG="false"
ENV VERIFY_SSL="true"
ENV TEMPERATURE="0.1"
ENV CONFIDENCE_THRESHOLD="0.5"
ENV PIPELINE_MODE="combined"
# Memory processing mode: off | distiller | neuralese | neuralese-distiller
# Override at runtime via Helm values (environment.MEMORY_MODE) or -e MEMORY_MODE=...
ENV MEMORY_MODE="distiller"
# Prompt env vars intentionally not set — built-in defaults from prompts.py used

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
