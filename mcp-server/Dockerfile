FROM python:3.14-slim AS base

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

COPY config.py api_client.py auth.py server.py mcp-clients.json pyproject.toml ./

ENV PORT=8080

RUN useradd -m app && chown -R app:app /app
USER app

EXPOSE 8080
CMD ["python", "server.py"]

FROM base AS dev

USER root
COPY requirements-dev.txt .
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements-dev.txt
COPY test_server.py .
RUN chown app:app requirements-dev.txt test_server.py
USER app
