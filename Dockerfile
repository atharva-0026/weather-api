FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p static
# Shell form (not exec form) so $PORT actually expands — Render injects
# its own PORT at runtime and requires the service to bind to it;
# hardcoding --port 8000 works on Railway but breaks on Render.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
