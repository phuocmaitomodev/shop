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
- `POST /auth/refresh`
- `POST /auth/logout`
- `GET /auth/me`
- `POST /auth/forgot-password`
- `POST /auth/reset-password`
- `GET /account/profile` (customer only)
- `PATCH /account/profile` (customer only; updates `full_name` and/or `phone`)
- `GET /admin/auth-check` (admin only)

Passwords use Argon2 hashes. Login creates a random opaque session token, stores only its SHA-256 hash in PostgreSQL, and sends the token in an HttpOnly, SameSite=Lax cookie. Set `AUTH_COOKIE_SECURE=true` when using HTTPS.

Refresh rotates the opaque token, extends the current session TTL, and invalidates the previous token without exposing either token in JSON. Account profile responses use the safe public user projection; profile updates cannot change email, role, active state, password hashes, or tokens.

Authentication mutations have a bounded in-process rate limit for the local single-API demo. Session/reset TTLs and rate-limit values come from environment variables. Production startup rejects `AUTH_COOKIE_SECURE=false`.

The local password-reset demo sends no email and never returns the reset token from an API response. The `forgot-password` response is identical for existing and unknown email addresses. After requesting a reset for a known local demo account, retrieve its short-lived token from the trusted local container shell:

```bash
docker compose exec api python -m app.cli.password_reset_token user@example.com
```

Submit that value as `token` together with `new_password` to `reset-password`. A successful reset consumes the token and revokes existing sessions. Treat the CLI output as a temporary secret and do not place it in source control or logs.

Public registration always creates a `customer`. Admin accounts are created by the deterministic seed in BE-06; the BE-04 API does not allow callers to choose or elevate their role.

## Public catalog

BE-05 adds the catalog migration `0003_catalog` and these public endpoints under `/api/v1`:

- `GET /categories` — active categories ordered by `sort_order`.
- `GET /products?page=1&page_size=20` — active product cards with exact integer VND prices, primary image, labels, and in-stock color/size availability.
- `GET /products/{slug}` — product detail with category, ordered images, labels, and active variants with live stock quantities.

Products in inactive categories, inactive products, and soft-deleted products are not exposed. Inactive variants are omitted; active zero-stock variants remain in detail responses with `is_available=false`. Search, facets, filters, sorting, and related products are intentionally deferred to BE-07.

### Deterministic demo catalog

After applying migrations, create or restore the canonical MVP dataset with:

```bash
docker compose --env-file .env.example run --rm api python -m app.cli.seed_catalog
```

The seed owns stable UUID/SKU/slug identities for 20 products in four categories,
plus their colors, sizes, primary placeholder images and 60 variants. Re-running it
updates those canonical rows in place and does not delete unrelated catalog data.
If an unrelated row already owns a canonical slug or SKU, the command exits nonzero
and rolls back instead of replacing that row.

Verify required fields, identities, relationships, prices, stock and idempotence by
running the verifier. The verifier intentionally performs one additional seed pass
and compares the persisted business-data snapshot before committing:

```bash
docker compose --env-file .env.example run --rm api python -m app.cli.verify_catalog
```

Both commands exit `0` on success and `1` on a validation, collision or database
error. Seed images use the internal `/media/placeholders/catalog-product.svg` asset
served by the API container.

## Tests and verification

```bash
docker build --target test -t shop-backend-test backend
docker run --rm shop-backend-test
docker compose --env-file .env.example config --quiet
docker compose --env-file .env.example run --rm api alembic heads
```

The default backend suite keeps fast tests self-contained and skips the PostgreSQL
migration integration test unless `MIGRATION_DATABASE_URL` is set. From the
repository root, run the same fresh-database check used by CI with:

```bash
docker compose --env-file .env.example \
  --project-name shop-migration-test --profile test \
  run --rm --build migration-test
docker compose --env-file .env.example \
  --project-name shop-migration-test --profile test \
  down --volumes --remove-orphans
```

This upgrades an empty `pgvector/pgvector:pg16` database to the current Alembic
head and asserts the revision, migrated tables, `vector` extension, retrieval
indexes, real vector writes, lease fencing, and `SKIP LOCKED` behavior. The test
intentionally rejects a reused database; clean the named project and volume after
every run, including failed runs.

To remove the local database volume and start clean:

```bash
docker compose down --volumes
```

## RAG index worker

`rag-worker` chạy `python -m app.rag.run_worker` và mặc định dùng provider
`stub` deterministic, nên local/CI không cần Gemini key. Worker claim từng job
trong transaction ngắn bằng `SELECT ... FOR UPDATE SKIP LOCKED`, commit lease
trước khi embed, rồi swap toàn bộ chunks và trạng thái job/document trong một
transaction. Job `processing` có lease quá hạn được đưa lại về `pending`.

Các biến vận hành:

- `EMBEDDING_DIMENSION=768` phải khớp migration `vector(768)`; startup fail-fast
  với giá trị khác.
- `RAG_WORKER_LOCK_TIMEOUT_SECONDS` phải lớn hơn thời gian xử lý/provider tệ nhất.
- `RAG_WORKER_PROVIDER_TIMEOUT_SECONDS` giới hạn mỗi lần gọi provider và phải nhỏ
  hơn lease timeout; timeout được phân loại retryable với mã `provider_timeout`.
- `RAG_WORKER_MAX_ATTEMPTS`, `RAG_WORKER_RETRY_BASE_SECONDS` và
  `RAG_WORKER_RETRY_MAX_SECONDS` điều khiển exponential backoff hữu hạn.
- `RAG_WORKER_POLL_SECONDS` là thời gian nghỉ khi queue không có job sẵn sàng.
- `RAG_WORKER_HEALTH_MAX_AGE_SECONDS` là tuổi tối đa của heartbeat file; healthcheck
  thất bại khi worker/DB iteration treo lâu hơn ngưỡng này. Giá trị nên lớn hơn
  provider timeout nhưng nhỏ hơn lease timeout.
- `RAG_WORKER_STOP_GRACE_PERIOD` là Compose stop grace period; mặc định dài hơn
  provider timeout để iteration đang chạy có thể kết thúc trước `SIGKILL`.

Lỗi retryable trở lại `pending` với `available_at` mới. Lỗi permanent hoặc hết
lần thử chuyển sang `failed`. `last_error` chỉ lưu mã lỗi kiểm soát, không lưu
raw provider response, stack trace, token hoặc secret. Event cũ hơn projection
được đánh dấu `succeeded` như superseded và không được sửa/xóa chunks mới.

Kiểm tra log và trạng thái worker:

```bash
docker compose ps rag-worker
docker compose logs rag-worker
```

Quan sát queue trực tiếp trong PostgreSQL (không in payload):

```sql
SELECT status, count(*) FROM rag_index_jobs GROUP BY status;
SELECT id, source_type, source_id, source_version, attempt_count,
       available_at, locked_at, last_error
FROM rag_index_jobs
WHERE status IN ('pending', 'processing', 'failed')
ORDER BY created_at, id;
```

`pending` có `available_at` tương lai là retry đang backoff. `processing` có
`locked_at` cũ hơn `RAG_WORKER_LOCK_TIMEOUT_SECONDS` sẽ được reclaim ở DB
iteration kế tiếp. Job `failed` là terminal; sau khi sửa nguyên nhân, thao tác
reindex phải tạo source version/job mới thay vì sửa hoặc hồi sinh job cũ. Worker
xử lý `SIGTERM`/`SIGINT`, dừng sau iteration hiện tại và xóa readiness marker.
