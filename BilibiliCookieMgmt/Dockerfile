FROM python:3.14-slim-trixie

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir fastapi uvicorn pyyaml httpx aiofiles

COPY . /app

EXPOSE 18000

CMD ["python", "main.py"]
