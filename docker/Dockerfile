# NSS v3.1.1 - Multi-stage Docker Build
FROM python:3.11-slim AS builder

WORKDIR /build
COPY pyproject.toml .
COPY README.md .
COPY src/ src/
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.11-slim

RUN groupadd -r nss && useradd -r -g nss -d /app -s /sbin/nologin nss

WORKDIR /app

COPY --from=builder /install /usr/local
COPY src/ src/

RUN chown -R nss:nss /app

USER nss

EXPOSE 11337

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://127.0.0.1:11337/health').raise_for_status()"

CMD ["uvicorn", "nss.gateway.server:app", "--host", "0.0.0.0", "--port", "11337"]
