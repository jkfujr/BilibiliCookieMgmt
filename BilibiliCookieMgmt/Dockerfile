FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir fastapi uvicorn pyyaml httpx aiofiles

COPY . /app

EXPOSE 18000

CMD ["python", "main.py"]
