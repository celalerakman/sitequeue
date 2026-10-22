# SiteQueue

A durable local job queue with expiring leases, bounded retries and fenced completion.

Idempotency keys deduplicate equivalent requests and reject conflicting payloads.
Claims are transactional. Expired workers cannot commit results after another worker
has reclaimed a job. Repeated failures and exhausted crash attempts reach dead letters.

## Run

Python 3.11 or newer; no external packages.

```sh
python -m sitequeue submit --key certificate-v1 --input examples/certificate-job.json
python -m sitequeue demo
python -m sitequeue health
python -m sitequeue show --id JOB_ID
python -m sitequeue worker
python -m unittest discover -s tests -v
```

The worker handles certificate calculations, ERP staging and content fingerprints.
Handlers are deterministic and have no external side effects. `demo` processes due
work and exits; `worker` continues polling. `replay --id JOB_ID` resets a dead job
after its cause has been addressed. SIGTERM/SIGINT stops the worker between jobs.

## Container

```sh
docker compose build
docker compose up -d
docker compose logs worker
docker compose down
```

The image runs as a non-root user and stores queue data in a named volume. Container
configuration is supplied; local Python tests exercise queue behavior independently.

## Delivery semantics

Processing is at least once. External effects need their own idempotency protocol.
Leases default to 30 seconds without heartbeat renewal. Workers share one local
SQLite database; this is not a multi-host queue. Health checks inspect database
integrity and counts, not an external worker heartbeat.
