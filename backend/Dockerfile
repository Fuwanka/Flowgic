# Один и тот же production-бандл используется Nginx и браузерными тестами.
FROM node:22.18.0-bookworm-slim AS spa-build
WORKDIR /web
COPY frontend-web/package*.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY frontend-web/ ./
RUN npm run build

FROM python:3.11-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends binutils gdal-bin libgeos-c1v5 libproj25 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

FROM base AS runtime
COPY --chown=app:app backend/ .
RUN chown app:app /app
USER app
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

FROM base AS test
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
COPY backend/requirements-dev.txt .
RUN pip install -r requirements-dev.txt
RUN playwright install-deps chromium
RUN playwright install --only-shell chromium
COPY --chown=app:app backend/ .
COPY --from=spa-build --chown=app:app /web/dist /spa
ENV SPA_DIST=/spa
RUN chown app:app /app
USER app
