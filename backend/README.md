# Backend foundation

## Local configuration

From the repository root, create the untracked runtime environment file:

```bash
cp .env.example .env
```

Replace the placeholder application and database secrets before sharing the environment. Gemini values are reserved for later RAG tasks and are not used by the foundation or authentication tasks.
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

## Authentication and RBAC

BE-04 provides these cookie-based endpoints under `/api/v1`:

- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/logout`
- `GET /auth/me`
- `POST /auth/forgot-password`
- `POST /auth/reset-password`
- `GET /admin/auth-check` (admin only)

Passwords use Argon2 hashes. Login creates a random opaque session token, stores only its SHA-256 hash in PostgreSQL, and sends the token in an HttpOnly, SameSite=Lax cookie. Set `AUTH_COOKIE_SECURE=true` when using HTTPS.

Authentication mutations have a bounded in-process rate limit for the local single-API demo. Session/reset TTLs and rate-limit values come from environment variables. Production startup rejects `AUTH_COOKIE_SECURE=false`.

The local password-reset demo sends no email and never returns the reset token from an API response. The `forgot-password` response is identical for existing and unknown email addresses. After requesting a reset for a known local demo account, retrieve its short-lived token from the trusted local container shell:

```bash
docker compose exec api python -m app.cli.password_reset_token user@example.com
```

Submit that value as `token` together with `new_password` to `reset-password`. A successful reset consumes the token and revokes existing sessions. Treat the CLI output as a temporary secret and do not place it in source control or logs.

Public registration always creates a `customer`. Admin accounts are created by the deterministic seed in BE-06; the BE-04 API does not allow callers to choose or elevate their role.

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
