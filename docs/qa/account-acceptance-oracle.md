# ACC-QA-00 — independent customer-account acceptance oracle

Status: acceptance specification only. At baseline `7ed49b3012ec3a5a773b3a47754d3ba201575ad2`, `/dang-nhap` and `/tai-khoan` are placeholders and `GET/PATCH /api/v1/account/profile` are not implemented. Do not report this checklist as passed until it is run against reviewed producer SHAs.

## 1. Frozen contract and release rule

Source: ACC-00 plus repository baseline `7ed49b3012ec3a5a773b3a47754d3ba201575ad2`.

Release is PASS only when all P0/P1 rows below pass on one clean PostgreSQL/API/browser integration, the focused and full suites/build pass, the exact backend/frontend SHAs are recorded, and no unexpected browser console/page/request errors occur. Any authorization, token-leak, persistence, immutable-field, or session-revocation failure is an immediate FAIL.

Non-goals: registration/reset UI, password/email change, order history implementation, social login, and admin dashboard.

## 2. Existing harness and deterministic fixtures

Current executable assets:

- Backend test image: `backend/Dockerfile` target `test`; default command is `pytest`.
- Backend auth fixture: `backend/tests/conftest.py` creates an isolated SQLite DB per test. `auth_client` preserves cookies; `create_auth_user(email, password="MatKhau-AnToan-123", role="customer")` can create customer/admin users; `register_customer` in `backend/tests/test_auth.py` creates a customer with `full_name="Khách Hàng Demo"` and `phone="0900000000"`.
- Existing auth coverage in `backend/tests/test_auth.py`: cookie login, wrong/unknown credentials, `/auth/me`, logout/session denial, customer→admin denial, admin admission, and safe user projection.
- Frontend runner: Vitest via `frontend/package.json`; API requests already use `credentials: "include"` and this is asserted in `frontend/src/tests/api-client.spec.ts`.
- Browser runner: Playwright `1.56.1` in `qa/`; projects are Chrome desktop `1366×768` and mobile `390×844`; failure traces/screenshots/video are retained. `qa/tests/e2e/application-shell.smoke.spec.ts` demonstrates collection of `pageerror`, error console messages, and failed requests.

Fixture gap at the baseline: there is no committed deterministic live customer/admin account seed or account Playwright spec. Public `/auth/register` can create live customer A/B, but never an admin. Clean-room admin integration must therefore use the backend `create_auth_user(..., role="admin")` test fixture, or a reviewed additive test-only PostgreSQL fixture. Never make public registration accept a role and never commit a real credential.

Canonical test identities (reserved documentation values, not production credentials):

| Fixture | Creation | Purpose |
|---|---|---|
| Customer A `account.a.qa@example.test` | API register or `create_auth_user` | login/profile/update/logout |
| Customer B `account.b.qa@example.test` | API register or `create_auth_user` | isolation oracle |
| Admin `account.admin.qa@example.test` | `create_auth_user(..., role="admin")` or reviewed test-only DB fixture | `CUSTOMER_REQUIRED` boundary |
| Password | runtime env `QA_ACCOUNT_PASSWORD`; test default may be `MatKhau-AnToan-123` | never print/store in artifacts |

Every run starts with new database state (or unique fixture emails) and a new browser context. Do not reuse a developer database or cookie jar.

## 3. Executable gates

Run from repository root after integrating the reviewed backend and frontend producer commits into a throwaway QA branch/worktree.

```bash
# Provenance and clean tree
git rev-parse HEAD
git status --short
git diff --check

# Backend focused + full suite. The producer must put profile cases in
# tests/test_auth.py or name the replacement file explicitly in handoff.
docker build --target test -t shop-account-qa-backend backend
docker run --rm shop-account-qa-backend \
  pytest -W error -q tests/test_auth.py -k 'login or logout or profile or admin'
docker run --rm shop-account-qa-backend pytest -W error -q

# Frontend full suite and production build
npm --prefix frontend ci
npm --prefix frontend test
npm --prefix frontend run build

# QA harness compile and case expansion. Account E2E must be tagged @account.
npm --prefix qa ci
node qa/node_modules/typescript/lib/tsc.js -p qa/tsconfig.json --noEmit
npm --prefix qa exec playwright test -- --list --grep @account \
  --project=chromium-desktop --project=chromium-mobile

# Live account browser gate after starting the reviewed isolated stack.
QA_BASE_URL=http://localhost:5176 \
QA_API_BASE_URL=http://localhost:8000/api/v1 \
npm --prefix qa exec playwright test -- --grep @account \
  --project=chromium-desktop --project=chromium-mobile
```

`--list` must show each browser-relevant account case in both projects. A zero-case result is FAIL, not a skip. The live browser command must use the same hostname (normally `localhost`) that is allow-listed by `CORS_ALLOWED_ORIGINS`; mixing `127.0.0.1` and `localhost` can create a false CORS/cookie failure.

For a disposable Compose lane, use a unique project name and ports if the defaults are occupied, then always remove its volume:

```bash
export COMPOSE_PROJECT_NAME=shop-account-qa
export API_PORT=18002 FRONTEND_PORT=15176 POSTGRES_PORT=15432
export CORS_ALLOWED_ORIGINS='["http://localhost:15176"]'
export VITE_API_BASE_URL=http://localhost:18002/api/v1

docker compose --env-file .env.example up -d db
docker compose --env-file .env.example run --rm api alembic upgrade head
docker compose --env-file .env.example up --build -d api frontend
docker compose --env-file .env.example ps

QA_BASE_URL=http://localhost:15176 \
QA_API_BASE_URL=http://localhost:18002/api/v1 \
npm --prefix qa exec playwright test -- --grep @account \
  --project=chromium-desktop --project=chromium-mobile

docker compose --env-file .env.example down --volumes --remove-orphans
```

If cleanup is needed after a failed run, execute the final `down --volumes --remove-orphans` command before retrying.

## 4. Compact acceptance checklist

### API, persistence, and security (P0)

- [ ] **ACC-API-01 Anonymous boundary.** With no cookie, `GET /api/v1/account/profile` and `PATCH /api/v1/account/profile` return `401`; envelope code is exactly `AUTH_REQUIRED`; no profile data is returned.
- [ ] **ACC-API-02 Customer cookie login.** Register/create Customer A, then `POST /api/v1/auth/login` with normalized email and valid password. Response is `200`, role is `customer`, body contains no token/session/password field, and `Set-Cookie` has the configured cookie name plus `HttpOnly`, `SameSite=Lax`, and `Path=/`. Cookie is `Secure` when HTTPS/production configuration requires it.
- [ ] **ACC-API-03 Wrong credentials.** Wrong password and unknown email both return `401 INVALID_CREDENTIALS` with the same public error shape. No authenticated cookie/session is created; a following profile GET remains `401 AUTH_REQUIRED`.
- [ ] **ACC-API-04 Live hydration.** After Customer A login, `GET /account/profile` returns the persisted A row through the existing `UserEnvelope`: only `id,email,full_name,phone,role,is_active` under `data`, plus request metadata. It never returns password/hash, cookie/session/token, reset token, or ownership internals.
- [ ] **ACC-API-05 Normalize and persist.** `PATCH {"full_name":"  Khách Hàng QA  ","phone":"  0901 234 567  "}` returns trimmed values. A new GET and a fresh browser reload return exactly the persisted normalized values.
- [ ] **ACC-API-06 Nullable phone.** PATCH with `phone: "   "` normalizes to `null` and persists; explicit `phone: null` is accepted and persists. A partial full-name-only patch preserves phone; a phone-only patch preserves full name.
- [ ] **ACC-API-07 Boundaries.** Full name lengths 1 and 200 after trim pass; blank/whitespace and 201 fail `422 VALIDATION_ERROR`. Phone length 32 after trim passes and 33 fails `422 VALIDATION_ERROR`. Failed validation performs no partial write.
- [ ] **ACC-API-08 Immutable/allow-list fields.** Probe separately with `email`, `role`, `is_active`, `password`, `password_hash`, `id`, `user_id`, `owner_id`, `session`, and `token` in PATCH. Each probe must be rejected by validation (preferred for a strict allow-list) and, regardless of status, a fresh DB/API read must prove email, role, active state, password hash, identity/ownership, and sessions unchanged. Do not combine probes; one request per forbidden field.
- [ ] **ACC-API-09 Customer isolation.** While authenticated as Customer A, profile GET/PATCH can only address A (there is no caller-controlled user ID). Customer B remains byte-for-byte unchanged after A updates. Query/path/body attempts to supply B's ID never select B.
- [ ] **ACC-API-10 Role boundary.** Admin cookie on GET/PATCH `/account/profile` returns `403 CUSTOMER_REQUIRED`; customer cookie on `/admin/auth-check` remains `403 ADMIN_REQUIRED`. Positive controls: customer profile succeeds and admin auth-check succeeds.
- [ ] **ACC-API-11 Logout revocation.** Capture the pre-logout cookie only inside the test process. `POST /auth/logout` returns `200`, clears the browser cookie, and revokes the server session. Both the current context and a new context replaying the captured old cookie receive `401 AUTH_REQUIRED` from `/auth/me` and `/account/profile`. A second logout remains safe/idempotent.
- [ ] **ACC-API-12 Token storage.** Raw session token appears only in the HttpOnly cookie during the test. PostgreSQL `auth_sessions.refresh_token_hash` is a 64-character SHA-256 hex digest and differs from the raw cookie. Login/profile/logout response bodies, URLs, logs, localStorage, sessionStorage, IndexedDB, rendered DOM, traces, and screenshots contain no raw token/password/hash. Redact the captured token from failure output.

### Browser behavior (P1 unless it exposes a P0 security failure)

- [ ] **ACC-UI-01 Anonymous account CTA.** Direct navigation to `/tai-khoan` calls the live profile endpoint, renders a Vietnamese unauthenticated state after `401 AUTH_REQUIRED`, and exposes a real internal link to `/dang-nhap`. It does not render stale profile data.
- [ ] **ACC-UI-02 Login success.** `/dang-nhap` has labelled email/password controls and submit button. Valid Customer A login uses the cookie-based API and routes to `/tai-khoan`; the account page hydrates from live `GET /account/profile`, not from the login response or hard-coded fixture.
- [ ] **ACC-UI-03 Login failure.** Wrong credentials show the stable Vietnamese API error, remain on login, do not leak account existence, do not create storage/cookie auth state, and permit a corrected retry.
- [ ] **ACC-UI-04 Loading and duplicate-submit safety.** Login/profile load/save/logout show a visible accessible pending state; controls that would duplicate a mutation are disabled while pending. Only one mutation request is emitted per action.
- [ ] **ACC-UI-05 Edit success/persistence.** Email is displayed read-only and no role/password/email-change control is offered. Edit full name/phone, save, see an accessible success state, reload the page/new context, and observe the normalized persisted values.
- [ ] **ACC-UI-06 Recoverable errors.** Stub or induce profile GET `500`/network failure: show a non-destructive Vietnamese error and a retry control; retry hydrates live data. Stub PATCH failure: retain the user's draft, show error, and do not display success. Expected 401 handling must not broadly suppress unrelated 401/403 console/network failures.
- [ ] **ACC-UI-07 Logout.** Logout calls the live endpoint, clears authenticated UI, and leaves `/tai-khoan` in the anonymous/login-CTA state. Back/reload cannot recover cached profile data; protected profile network calls remain denied.
- [ ] **ACC-UI-08 Responsive/accessibility.** Run success, anonymous, error/retry, and edit states at 1366×768 and 390×844. No horizontal overflow, clipped fields, or chat-widget overlap; touch targets remain usable; headings/labels/status messages are accessible; keyboard focus is visible and follows the interaction.
- [ ] **ACC-UI-09 Internal links and shell.** Login CTA resolves to named `/dang-nhap`; post-login and logout destinations resolve without full-page 404; existing header/home links remain valid. No placeholder copy remains on `/dang-nhap` or `/tai-khoan`.
- [ ] **ACC-UI-10 Runtime cleanliness.** Collect `pageerror`, console errors, and `requestfailed` for every account test. Also fail unexpected HTTP `>=400`; allow only the exact endpoint/status intentionally exercised by anonymous, wrong-login, role-denial, or injected-error cases. Final collection is empty after scoped expected failures are removed.

## 5. Required automated assertions

The producer/release branch must provide, at minimum:

1. Backend tests for ACC-API-01 through ACC-API-11; ACC-API-12 must include response projection and stored-hash checks.
2. Frontend service tests asserting exact methods/paths/payloads and cookie credentials; page tests for success, wrong login, 401 CTA, loading, retry, update, logout, and immutable UI.
3. Playwright `@account` tests for ACC-UI-01 through 10 against the live API for the happy path/logout/persistence. Mocked browser tests may cover deterministic 500/network rendering, but must not be described as backend authorization evidence.
4. Desktop and mobile project expansion verified with `playwright test --list`.

## 6. Evidence handoff

Record all of the following in ACC-QA-01:

- baseline, reviewed backend SHA, reviewed frontend SHA, and QA integration SHA;
- exact commands and pass/fail/skip counts for focused backend, full backend, full frontend, build, TypeScript compile, Playwright `--list`, and live Playwright;
- fixture creation method and isolated Compose project/ports;
- failing acceptance ID plus exact endpoint, status/error code, browser project, and minimal repro for every failure;
- browser trace/screenshot path only for failures, with credentials/tokens redacted;
- `git status --short`, `git diff --check`, cleanup result, and explicit statement that nothing was pushed or merged to main.

## 7. Known risks at baseline

- No deterministic live admin fixture exists; without a reviewed test-only fixture, PostgreSQL/browser evidence for admin→customer denial is incomplete even if SQLite unit coverage passes.
- Existing Playwright smoke still identifies `/dang-nhap` and `/tai-khoan` as placeholders. Producer integration must update or replace those expectations; leaving both old placeholder tests and new account tests can produce misleading coverage.
- Existing Playwright runtime collection treats every failed request as unexpected. Account negative cases need narrow endpoint/status scoping, not a blanket 401/403 suppression.
- Hostname mismatch (`localhost` versus `127.0.0.1`) changes origin/cookie behavior. Keep frontend URL, CORS allow-list, and API host intentional and record them.
- Frontend unit tests with mocked fetch do not prove HttpOnly cookies, server-side revocation, RBAC, PostgreSQL persistence, or raw-token hashing. Those claims require the live API/DB lane.
- The ACC-00 contract does not define concurrent profile-write/version semantics. Do not invent optimistic concurrency as a release gate; last-write behavior is a documented residual risk unless the contract is amended.
