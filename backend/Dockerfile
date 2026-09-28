FROM docker.io/library/python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/synergia/backend

WORKDIR /opt/synergia/backend

COPY backend/requirements.txt requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt

RUN groupadd --gid 10001 synergia \
    && useradd --uid 10001 --gid synergia --no-log-init \
        --home-dir /opt/synergia --no-create-home synergia \
    && mkdir -p \
        /var/lib/synergia/imports \
        /var/lib/synergia/avatars \
        /var/lib/synergia/email-capture \
    && chown -R synergia:synergia /var/lib/synergia

COPY --chown=synergia:synergia backend/app app
COPY --chown=synergia:synergia scripts/apply_migrations.py scripts/apply_migrations.py
COPY --chown=synergia:synergia database/migrations database/migrations

USER 10001:10001
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
