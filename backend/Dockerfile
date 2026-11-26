FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 app
WORKDIR /srv
COPY pyproject.toml .
COPY app ./app
RUN pip install --no-cache-dir .
COPY main.py alembic.ini ./
COPY migrations ./migrations
USER app
EXPOSE 8000
# --proxy-headers: nginx is the only thing that can reach this port, so X-Forwarded-For is trusted (rate limits need the real client IP)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
