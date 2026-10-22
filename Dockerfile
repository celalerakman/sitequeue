FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 QUEUE_DB=/data/queue.sqlite
WORKDIR /app
COPY sitequeue /app/sitequeue
RUN useradd --uid 10001 --create-home worker && mkdir /data && chown worker /data
USER worker
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s CMD python -m sitequeue health || exit 1
CMD ["python", "-m", "sitequeue", "worker"]
