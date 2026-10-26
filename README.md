# Shop demo

Website bán quần áo mẫu chạy local bằng Docker Compose, gồm Vue 3, FastAPI,
PostgreSQL/pgvector và worker lập chỉ mục RAG bền vững.

## Khởi chạy local

Yêu cầu Docker Engine và Docker Compose v2.

```bash
cp .env.example .env
docker compose up -d db
docker compose run --rm api alembic upgrade head
docker compose run --rm api python -m app.cli.seed_catalog
docker compose run --rm api python -m app.cli.verify_catalog
docker compose run --rm api python -m app.cli.reindex_products
docker compose up --build -d
docker compose ps
```

Phải migrate trước khi khởi động toàn stack; nếu chạy worker trên database chưa có
schema, worker sẽ retry và ghi lỗi cho đến khi migration hoàn tất.

Trước khi chia sẻ môi trường, thay các giá trị `change-me-*` trong `.env` và giữ
`POSTGRES_PASSWORD` đồng bộ với mật khẩu đã URL-encode trong `DATABASE_URL`.
Không đưa Gemini API key thật vào source control.

Các địa chỉ local mặc định:

- Frontend: http://localhost:5176
- API docs: http://localhost:8000/docs
- API liveness: http://localhost:8000/api/v1/health/live
- API readiness: http://localhost:8000/api/v1/health/ready

`rag-worker` claim outbox bằng `FOR UPDATE SKIP LOCKED`, dùng lease để phục hồi
job bị gián đoạn và chạy provider deterministic offline theo mặc định. Xem cấu
hình retry và hướng dẫn vận hành trong [`backend/README.md`](backend/README.md).
Đặt `RAG_EMBEDDING_PROVIDER=gemini`, `RAG_CHAT_PROVIDER=gemini` cùng
`GEMINI_API_KEY`, `GEMINI_MODEL` và `GEMINI_EMBEDDING_MODEL` trong `.env` để
dùng Gemini; không cần key khi dùng stub deterministic mặc định.

## Kiểm tra và dọn môi trường

```bash
docker compose --env-file .env.example config --quiet
docker compose ps
docker compose logs rag-worker
docker compose down
```

## Chạy release gate

Các lệnh local release gate:

```bash
# Backend (integration PostgreSQL được tách riêng và sẽ skip ở suite này)
docker build --target test --tag shop-backend-test backend
docker run --rm shop-backend-test

# Frontend
npm --prefix frontend ci
VITE_API_BASE_URL=http://localhost:8000/api/v1 npm --prefix frontend test
VITE_API_BASE_URL=http://localhost:8000/api/v1 npm --prefix frontend run build

# E2E trên stack Compose đã migrate, seed và reindex
npm --prefix qa ci
node qa/node_modules/typescript/lib/tsc.js -p qa/tsconfig.json --noEmit
QA_BASE_URL=http://127.0.0.1:5176 \
QA_API_BASE_URL=http://127.0.0.1:8000/api/v1 \
npm --prefix qa run test:mvp

# Alembic upgrade trên PostgreSQL/pgvector hoàn toàn mới
docker compose --env-file .env.example \
  --project-name shop-migration-test --profile test \
  run --rm --build migration-test
docker compose --env-file .env.example \
  --project-name shop-migration-test --profile test \
  down --volumes --remove-orphans
```

Integration test yêu cầu database trống và xác minh Alembic ở đúng head,
schema pgvector cùng cơ chế claim/lease PostgreSQL hoạt động. Luôn chạy lệnh
`down --volumes` ở cuối (kể cả khi test lỗi) trước khi chạy lại cùng project name.

Để xóa cả dữ liệu PostgreSQL local và khởi tạo lại từ đầu:

```bash
docker compose down --volumes
```

Hướng dẫn backend, migration, catalog seed/reindex và RAG worker chi tiết nằm trong
[`backend/README.md`](backend/README.md). Không có seed hoặc reindex ngầm khi khởi
động Compose.
