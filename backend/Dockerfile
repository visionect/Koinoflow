FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV DJANGO_SETTINGS_MODULE=config.settings.production
ENV SECRET_KEY=build-time-secret
ENV DATABASE_URL=postgres://koinoflow:koinoflow@localhost:5432/koinoflow
ENV FRONTEND_URL=http://localhost:5173
ENV PORT=8080

RUN python manage.py collectstatic --noinput
RUN useradd -m app && chown -R app:app /app

USER app

EXPOSE 8080
CMD ["sh", "-c", "exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 120"]
