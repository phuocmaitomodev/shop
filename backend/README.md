# Backend foundation

## Local configuration

From the repository root, create the untracked runtime environment file:

```bash
cp .env.example .env
```

Replace the placeholder application and database secrets before sharing the environment. Keep `RAG_EMBEDDING_PROVIDER=stub` and `RAG_CHAT_PROVIDER=stub` for deterministic offline development, or configure the Gemini values described below.
When changing the PostgreSQL password, update the URL-encoded password in `DATABASE_URL` to match it.

## Run API and PostgreSQL

```bash
docker compose up -d db
docker compose run --rm api alembic upgrade head
docker compose up --build -d api rag-worker frontend
docker compose ps
```

Không khởi động `rag-worker` trước migration: worker cần các bảng outbox/chunk và
sẽ retry với log lỗi khi schema chưa tồn tại.

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
- `GET /products?page=1&page_size=20` — active product cards with exact integer VND prices, primary image, labels, and in-stock color/size availability. Optional `q`, `category`, `min_price`, `max_price`, `color`, and `size` parameters can be combined.
- `GET /products/{slug}` — product detail with category, ordered images, labels, and active variants with live stock quantities.

Products in inactive categories, inactive products, and soft-deleted products are not exposed. Inactive variants are omitted; active zero-stock variants remain in detail responses with `is_available=false`. Search and catalog filters are implemented; facets, sorting, and related products remain outside the current MVP contract.

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

### Deterministic return-policy source

After catalog projection, seed the canonical Vietnamese return policy and verify its
knowledge source, RAG projection, checksum, current version and index outbox job:

```bash
docker compose --env-file .env.example run --rm api python -m app.cli.seed_return_policy
docker compose --env-file .env.example run --rm api python -m app.cli.verify_return_policy
```

The seed owns stable UUIDs for the policy source, projection and each versioned job.
An unchanged rerun creates no new row or job. A canonical content change advances
the source and projection once and enqueues exactly one job for the new version. A
collision or partial/mismatched state exits nonzero and the first seed transaction
rolls back atomically.

### Product projection and reindex

After seeding, synchronize public catalog products into the durable RAG projection
and enqueue changed versions with:

```bash
docker compose --env-file .env.example run --rm api python -m app.cli.reindex_products
```

The command is idempotent: unchanged products do not create another job. Name,
category and description are projected for semantic retrieval. Price, sale price,
color, size and stock are deliberately excluded and must be hydrated from PostgreSQL
when answering a chat request. Inactive, soft-deleted, category-inactive and orphaned
products enqueue a versioned delete event.

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

## Product chat API

`POST /api/v1/chat` nhận `message` và tối đa 6 lượt `history`, không lưu transcript.
Response trả `answer`, product cards SQL-hydrated, source IDs đã allow-list và một
trong các status `ok`, `insufficient_data`, `out_of_scope`,
`provider_unavailable`. Stub deterministic là mặc định. Để dùng Gemini cho
structured planning/selection, đặt `RAG_CHAT_PROVIDER=gemini`, `GEMINI_API_KEY`
và `GEMINI_MODEL`; dynamic price/stock vẫn luôn được render từ PostgreSQL.
API giới hạn theo IP với `CHAT_RATE_LIMIT_REQUESTS` trong cửa sổ
`CHAT_RATE_LIMIT_WINDOW_SECONDS` để bảo vệ provider công khai.

## RAG index worker

`rag-worker` chạy `python -m app.rag.run_worker` và mặc định dùng provider
`stub` deterministic, nên local/CI không cần Gemini key. Worker claim từng job
trong transaction ngắn bằng `SELECT ... FOR UPDATE SKIP LOCKED`, commit lease
trước khi embed, rồi swap toàn bộ chunks và trạng thái job/document trong một
transaction. Job `processing` có lease quá hạn được đưa lại về `pending`.

Các biến vận hành:

- `RAG_EMBEDDING_PROVIDER=stub|gemini` chọn provider. Với `gemini`, phải cấu hình
  cả `GEMINI_API_KEY` và `GEMINI_EMBEDDING_MODEL`; worker fail-fast nếu thiếu.
- Gemini key chỉ được gửi trong header `x-goog-api-key`, không được ghi log hoặc
  commit. Adapter yêu cầu output 768 chiều và chuẩn hóa L2 trước khi lưu.
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

## Product retrieval and live hydration

`app.rag.retrieval.retrieve_products` nhận vector truy vấn 768 chiều, hard filters
`category`, `min_price`, `max_price`, `color`, `size` và limit tối đa 20. Candidate
chỉ đến từ product document đang active/indexed cùng active chunk đúng
`source_version`; ranking và limit được áp dụng theo product để nhiều chunk của một
product không lấn át product khác. Category, effective price và một biến thể còn
hàng thỏa đồng thời color/size đều được lọc bằng SQL.

Sau semantic selection, hàm revalidate document/chunk và hydrate name, slug, ảnh,
effective price, màu, size và stock từ catalog PostgreSQL trong một câu SQL cuối.
Kết quả chỉ expose product/source/chunk IDs thuộc retrieval set đã xác thực; dữ liệu
động trong embedding hoặc chunk content không được dùng làm nguồn trả lời.
