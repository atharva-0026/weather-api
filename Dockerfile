FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install fastapi uvicorn httpx redis slowapi python-dotenv
COPY . .
RUN mkdir -p static
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
