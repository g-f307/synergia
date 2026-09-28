FROM docker.io/library/python:3.14-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/synergia/backend

WORKDIR /opt/synergia/backend

COPY backend/requirements.txt requirements.txt
RUN apk upgrade --no-cache \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip uninstall --yes pip

RUN addgroup --gid 10001 --system synergia \
    && adduser --uid 10001 --ingroup synergia --system \
        --home /opt/synergia --no-create-home synergia \
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
