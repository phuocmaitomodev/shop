# Backend foundation

## Local configuration

From the repository root, create the untracked runtime environment file:

```bash
cp .env.example .env
```

Replace the placeholder application and database secrets before sharing the environment. Gemini values are reserved for later RAG tasks and are not used by BE-01 through BE-03.
When changing the PostgreSQL password, update the URL-encoded password in `DATABASE_URL` to match it.

## Run API and PostgreSQL

```bash
docker compose up --build -d
docker compose ps
docker compose exec api alembic upgrade head
```

Endpoints:

- Liveness: `http://localhost:8000/api/v1/health/live`
- Readiness (includes PostgreSQL): `http://localhost:8000/api/v1/health/ready`
- OpenAPI: `http://localhost:8000/docs`

## Tests and verification

```bash
docker build --target test -t shop-backend-test backend
docker run --rm shop-backend-test
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example run --rm api alembic heads
```

To remove the local database volume and start clean:

```bash
docker compose down --volumes
```
