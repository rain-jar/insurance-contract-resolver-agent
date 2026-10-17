FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CONTRACT_STACK_DATA_DIR=/data \
    CONTRACT_STACK_DATABASE=/data/contract-stack.sqlite3 \
    CONTRACT_STACK_HOST=0.0.0.0 \
    PORT=8000

RUN apt-get update \
    && apt-get install --no-install-recommends -y tesseract-ocr \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system contractstack \
    && useradd --system --gid contractstack --create-home contractstack

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . \
    && mkdir -p /data \
    && chown contractstack:contractstack /data

USER contractstack
EXPOSE 8000
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

CMD ["contract-stack-api"]
