FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system executor && adduser --system --ingroup executor executor

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY executor ./executor

USER executor

ENTRYPOINT ["python", "-m", "executor.run"]
