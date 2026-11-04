# FitCheck.AI server image (any container host). Runs as a non-root user.
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY . .
RUN rm -rf tests notebooks scripts .github && useradd --create-home --uid 10001 fitcheck
USER fitcheck
WORKDIR /app/backend
EXPOSE 8000
CMD ["sh", "-c", "python init_db.py && gunicorn wsgi:app --bind 0.0.0.0:${PORT:-8000} --workers 2 --threads 4 --timeout 150"]
