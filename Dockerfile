FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt requirements-production.txt ./
RUN pip install --no-cache-dir -r requirements-production.txt
RUN useradd --uid 10001 --create-home memoria \
    && mkdir -p /var/lib/memoria/media /var/www/static \
    && chown -R memoria:memoria /var/lib/memoria /var/www/static
COPY --chown=memoria:memoria manage.py ./
COPY --chown=memoria:memoria config ./config
COPY --chown=memoria:memoria snippets ./snippets
COPY --chown=memoria:memoria deploy/entrypoint.sh ./deploy/entrypoint.sh
USER memoria
EXPOSE 8000
ENTRYPOINT ["sh", "/app/deploy/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind=0.0.0.0:8000", "--workers=2", "--access-logfile=-", "--error-logfile=-", "--forwarded-allow-ips=*"]
