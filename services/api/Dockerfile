# Build context: repository root.
FROM python:3.12.11-slim-bookworm AS deps
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv
COPY services/api/requirements.txt .
RUN pip install -r requirements.txt

# A failed lint or test stops the image build.
FROM deps AS test
COPY services/api/requirements-dev.txt .
RUN pip install -r requirements-dev.txt
COPY services/api/ .
RUN ruff check --no-cache . \
    && ruff format --no-cache --check . \
    && pytest -q -p no:cacheprovider -m "not integration"

FROM deps AS runtime
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin niyam
COPY services/api/app ./app
# Last, so a new git SHA does not invalidate the dependency layers.
ARG APP_VERSION=dev
ENV NIYAM_APP_VERSION=${APP_VERSION}
USER 10001
EXPOSE 8000
CMD ["uvicorn", "app.main:build_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--timeout-graceful-shutdown", "25"]
