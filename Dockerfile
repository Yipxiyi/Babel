FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BABEL_HOST=0.0.0.0 \
    BABEL_PORT=7860 \
    BABEL_DATA_DIR=/data

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir .

VOLUME ["/data"]
EXPOSE 7860

CMD ["babel-server", "--host", "0.0.0.0", "--port", "7860", "--data-dir", "/data"]
