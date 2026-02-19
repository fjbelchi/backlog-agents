FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir \
    "flask>=3.0,<4" \
    "chromadb>=0.5,<1" \
    "sentence-transformers>=2.7,<4"

# Copy server script
COPY scripts/rag/server.py /app/server.py

EXPOSE 8001

CMD ["python3", "server.py", "--host", "0.0.0.0", "--port", "8001", "--db-path", "/data/chroma"]
