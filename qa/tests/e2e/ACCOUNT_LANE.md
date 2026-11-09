# Isolated customer-account E2E lane

This lane runs only PostgreSQL, migrations, the API, and the Vite frontend needed by
`account.spec.ts`. It does not use a developer database or the repository `.env`.
All credentials in the Compose file are fixed test-only values, and the project-scoped
volume is deleted during teardown.

## Frozen producer contracts

The lane was prepared against backend `9551415c2758c5eae13fa57d92a3b5bc1c022c6d`
and frontend `3cf8b9e49c3f09c4702d40ae91315f3314a0e8de`.

Relevant API calls (base path `/api/v1`):

- `POST /auth/register`: public fixture creation; `201` and a safe `UserEnvelope`.
- `POST /auth/login`: email/password login; `200`, safe `UserEnvelope`, and the
  HttpOnly `shop_account_e2e_session` cookie (`SameSite=Lax`, `Path=/`).
- `GET /account/profile`: customer hydration; anonymous or revoked sessions get
  `401 AUTH_REQUIRED`.
- `PATCH /account/profile`: customer-only update of `full_name` and `phone`; values
  are normalized and persisted in PostgreSQL.
- `POST /auth/logout`: revokes the server session, expires the cookie, and returns
  `{"data":{"status":"logged_out"},...}`.

The frontend API client uses `credentials: "include"`. Therefore the frontend URL,
API URL, and API CORS origin intentionally use the same exact hostname:
`127.0.0.1`. Do not substitute `localhost` in only one of them.

## Ports and environment

Defaults:

- PostgreSQL: `127.0.0.1:15432`, database/user `account_e2e`.
- API: `http://127.0.0.1:18002/api/v1`.
- Frontend: `http://127.0.0.1:15176`.
- API CORS allow-list: exactly `["http://127.0.0.1:15176"]`.
- Browser cookie name: `shop_account_e2e_session`.

Set a unique `ACCOUNT_E2E_PROJECT_NAME` for every lane. Compose intentionally
fails before creating resources when it is missing; this prevents concurrent QA
runs from recreating each other's containers or sharing a PostgreSQL volume.

Ports can be overridden with `ACCOUNT_E2E_POSTGRES_PORT`,
`ACCOUNT_E2E_API_PORT`, and `ACCOUNT_E2E_FRONTEND_PORT`. If a port changes, use
the same value in the Playwright environment shown below; Compose interpolates the
matching CORS origin and frontend API URL.

The lane uses `10.252.27.0/24` by default so it can still start on hosts whose
Docker predefined address pools are exhausted. Override `ACCOUNT_E2E_SUBNET` with
another unused private `/24` if that subnet conflicts with a local route.

## Start, inspect, discover, and run

Run from the repository root:

```bash
export ACCOUNT_E2E_PROJECT_NAME=shop-account-e2e-my-run
COMPOSE_FILE=qa/tests/e2e/account-lane.compose.yml

docker compose -f "$COMPOSE_FILE" up --build --wait db api frontend
docker compose -f "$COMPOSE_FILE" ps
curl --fail http://127.0.0.1:18002/api/v1/health/ready
curl --fail http://127.0.0.1:15176/

npm --prefix qa ci
node qa/node_modules/typescript/lib/tsc.js -p qa/tsconfig.json --noEmit

QA_BASE_URL=http://127.0.0.1:15176 \
QA_API_BASE_URL=http://127.0.0.1:18002/api/v1 \
QA_ACCOUNT_COOKIE_NAME=shop_account_e2e_session \
npm --prefix qa exec playwright test -- --list --grep @account \
  --config qa/playwright.config.ts \
  --project=chromium-desktop --project=chromium-mobile

QA_BASE_URL=http://127.0.0.1:15176 \
QA_API_BASE_URL=http://127.0.0.1:18002/api/v1 \
QA_ACCOUNT_COOKIE_NAME=shop_account_e2e_session \
QA_ACCOUNT_RUN_ID="manual-$(date +%s)" \
npm --prefix qa exec playwright test -- --grep @account \
  --config qa/playwright.config.ts \
  --project=chromium-desktop --project=chromium-mobile --workers=1
```

`account.spec.ts` creates each customer through `POST /auth/register`; it never uses
the registration UI. Each email contains the Playwright project, a run namespace,
and a random UUID suffix, so parallel desktop/mobile runs and retries do not share a
customer. The dedicated database volume is the cleanup boundary.

Always tear down, including after a failed run:

```bash
export ACCOUNT_E2E_PROJECT_NAME=shop-account-e2e-my-run
docker compose -f qa/tests/e2e/account-lane.compose.yml down --volumes --remove-orphans
```

A nonzero `@account` count must be listed in both projects. `--list` proves discovery
only; it is not evidence that cookie auth or PostgreSQL persistence passed.
