FROM node:20-slim AS web-builder

WORKDIR /app
COPY web/package*.json ./web/
RUN npm ci --prefix web
COPY web ./web
COPY docs/assets/brand ./docs/assets/brand
COPY src/babel_epub ./src/babel_epub
RUN npm run build --prefix web

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BABEL_HOST=0.0.0.0 \
    BABEL_PORT=7860 \
    BABEL_DATA_DIR=/data

WORKDIR /app
COPY . /app
COPY --from=web-builder /app/src/babel_epub/static /app/src/babel_epub/static
RUN apt-get update \
    && apt-get install -y --no-install-recommends calibre \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir .

VOLUME ["/data"]
EXPOSE 7860

CMD ["babel-server", "--host", "0.0.0.0", "--port", "7860", "--data-dir", "/data"]
