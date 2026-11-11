# syntax=docker/dockerfile:1
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/opt/venv/bin:$PATH"
WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
# Las herramientas de compilación se eliminan en la misma capa. El certificado
# de la sesión, cuando existe, solo se monta durante las descargas.
RUN --mount=type=secret,id=ca_bundle,required=false,mode=0444 \
    if [ -f /run/secrets/ca_bundle ]; then \
      printf 'Acquire::https::CaInfo "/run/secrets/ca_bundle";\n' > /etc/apt/apt.conf.d/99buildca; \
      export PIP_CERT=/run/secrets/ca_bundle; \
    fi; \
    apt-get update \
    && apt-get install -y --no-install-recommends gcc default-libmysqlclient-dev pkg-config libmariadb3 \
    && python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt \
    && apt-get purge -y --auto-remove gcc default-libmysqlclient-dev pkg-config \
    && rm -rf /var/lib/apt/lists/* /tmp/requirements.txt \
    && rm -f /etc/apt/apt.conf.d/99buildca \
    && useradd --create-home --uid 10001 app \
    && mkdir -p logs media staticfiles .local \
    && chown -R app:app logs media staticfiles .local \
    && chmod 700 .local
COPY --chown=app:app . .
USER app
EXPOSE 8000
ENTRYPOINT ["sh", "docker/entrypoint.sh"]
CMD ["gunicorn", "--config", "config/gunicorn.conf.py", "SENNOVA.wsgi:application"]
