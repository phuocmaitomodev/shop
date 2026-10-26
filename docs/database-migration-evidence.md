# Đối chiếu migration, schema và cấu hình dữ liệu

## 1. Phạm vi và cách đọc

Tài liệu này là ảnh chụp bằng chứng của repository trên nhánh hiện tại. Nó không
thay đổi contract trong `docs/database-schema.md`, public API hoặc event contract.
`docs/database-schema.md` vẫn là schema **dự kiến**; bảng dưới đây phân biệt rõ
phần đã có migration với phần mới chỉ là thiết kế.

Nguồn đã đối chiếu:

- yêu cầu gốc: `request.md`, nhất là mục 4, 6 và 8.1;
- contract/schema: `docs/database-schema.md` và `docs/architecture.md`;
- lệnh vận hành: `README.md`, `backend/README.md`, `docker-compose.yml`;
- chuỗi Alembic: `backend/alembic/versions/0001_*.py` đến `0005_*.py`;
- metadata ORM: `backend/app/models/*.py`, `backend/app/db/base.py`;
- cấu hình runtime: `backend/app/core/config.py`, `.env.example`;
- kiểm chứng PostgreSQL mới: `backend/tests/integration/test_postgres_migrations.py`
  và `backend/tests/test_rag_index_postgres.py`.

Ký hiệu mức độ khớp:

- **Khớp**: migration/ORM/runtime hiện tại xác nhận mô tả.
- **Khớp một phần**: có implementation nhưng default, lớp enforcement hoặc phạm
  vi khác với cách tài liệu đang diễn đạt.
- **Chưa hỗ trợ**: contract có mô tả nhưng branch chưa có migration/model/seed.
- **Sai thời điểm**: tài liệu ghi trạng thái branch cũ, không còn đúng với tree này.

## 2. Lệnh, thứ tự và revision Alembic

| Nội dung tài liệu | Bằng chứng repository | Giá trị thực tế | Mức độ | Nội dung cần sửa/làm tiếp |
|---|---|---|---|---|
| Chạy migration bằng `docker compose exec api alembic upgrade head` (`README.md:10-15`, `backend/README.md:16-20`) | `backend/alembic/env.py:8-16,19-59`; `docker-compose.yml:20-55` | URL lấy từ `Settings.database_url`; API không tự migrate khi start, lệnh phải chạy sau khi container lên | Khớp | Giữ lệnh hiện tại; không mô tả migration là tự động |
| Kiểm tra head bằng Compose (`backend/README.md:71-76`) | `backend/tests/test_database_foundation.py:72-92` | Một head duy nhất: `0005_rag_chunks` | Khớp | Không có |
| Fresh-database lane (`README.md:55-66`, `backend/README.md:78-95`) | `docker-compose.yml:57-78`; `backend/tests/integration/test_postgres_migrations.py:46-97` | Profile `test` yêu cầu DB trống, chạy `upgrade head`, kiểm tra revision/table/extension | Khớp | Sau mỗi lượt phải `down --volumes --remove-orphans` |
| Thứ tự dự kiến extensions/enums → identity → catalog → cart/pricing → orders/inventory → knowledge/vector → chat/support → indexes (`docs/database-schema.md:206-209`) | revision/down-revision trong 5 file migration | `0001_enable_pgvector` → `0002_identity_auth` → `0003_catalog` → `0004_rag_content` → `0005_rag_chunks` | Khớp một phần | Chuỗi hiện tại bỏ qua các phase chưa triển khai; cart/order/chat không được ngầm xem là đã migrate |
| Branch chưa chứa dependency/schema/worker (`docs/rag-outbox-dependency-report.md:27`, `docs/rag-outbox-claim-design.md:5-7`) | Tree hiện có `0004`, `0005`, models, producer, worker và tests; head là `0005_rag_chunks` | Nhận định trạng thái branch này đã cũ | Sai thời điểm | Khi bảo trì hai tài liệu thiết kế, thay đoạn trạng thái branch bằng tham chiếu commit/tree hiện hành; không đổi contract |

Chuỗi revision xác nhận trực tiếp:

| Revision | `down_revision` | Side effect chính | Bằng chứng |
|---|---|---|---|
| `0001_enable_pgvector` | `None` | `CREATE EXTENSION IF NOT EXISTS vector`; downgrade drop extension | `backend/alembic/versions/0001_enable_pgvector.py:12-23` |
| `0002_identity_auth` | `0001_enable_pgvector` | `users`, `auth_sessions`, `password_reset_tokens` | `backend/alembic/versions/0002_identity_auth.py:14-121` |
| `0003_catalog` | `0002_identity_auth` | 8 bảng catalog và index/constraint liên quan | `backend/alembic/versions/0003_catalog.py:14-254` |
| `0004_rag_content` | `0003_catalog` | `knowledge_documents`, `rag_documents`, `rag_index_jobs` | `backend/alembic/versions/0004_rag_content.py:14-171` |
| `0005_rag_chunks` | `0004_rag_content` | `rag_chunks`, HNSW cosine, FTS GIN | `backend/alembic/versions/0005_rag_chunks.py:15-99` |

## 3. Ma trận schema đã triển khai

Quy ước trong cột “Cột thực tế”:

- mọi cột không có dấu `?` là `NOT NULL`; `?` là nullable;
- `db=...` là server default; `app=...` chỉ là default của ORM/Python;
- UUID primary key có `app=uuid4`, **không** có database default;
- các bảng dùng `TimestampMixin` có `created_at timestamptz db=now()` và
  `updated_at timestamptz db=now(), app-on-update=now()`; database không có trigger
  tự cập nhật `updated_at` cho SQL ngoài ORM.

| Contract/tài liệu | Cột thực tế (type, nullable, default) | Constraint/index thực tế | Bằng chứng migration / ORM | Mức độ và ghi chú |
|---|---|---|---|---|
| `users` (`docs/database-schema.md:15-19`) | `id uuid`; `email varchar(320)`; `password_hash varchar(255)`; `full_name varchar(200)`; `phone varchar(32)?`; `role varchar(20) app=customer`; `is_active bool app=true`; timestamps | PK `id`; unique index `email`; CHECK role `customer|admin` | `0002_identity_auth.py:21-47`; `models/auth.py:18-36`; lowercase tại `schemas/auth.py:13-16` | Khớp một phần: DB unique là case-sensitive; lowercase do API validator, không phải DB constraint. `role/is_active` không có server default |
| `auth_sessions` (`database-schema.md:21-24`) | `id uuid`; `user_id uuid`; `refresh_token_hash varchar(64)`; `expires_at timestamptz`; `revoked_at timestamptz?`; `user_agent varchar(512)?`; `created_at db=now()` | FK user `ON DELETE CASCADE`; unique token hash; index `user_id`; index `(user_id, expires_at)` | `0002_identity_auth.py:49-79`; `models/auth.py:46-66` | Khớp; `user_agent` là metadata thực tế được tài liệu mô tả tổng quát |
| `password_reset_tokens` (`database-schema.md:26-29`) | `id uuid`; `user_id uuid`; `token_hash varchar(64)`; `expires_at timestamptz`; `used_at timestamptz?`; `created_at db=now()` | FK user cascade; unique index token hash; index user | `0002_identity_auth.py:81-110`; `models/auth.py:69-83` | Khớp |
| `categories` (`database-schema.md:33-36`) | `id uuid`; `name varchar(120)`; `slug varchar(140)`; `description text?`; `sort_order int app=0`; `is_active bool app=true`; timestamps | unique slug; CHECK `sort_order >= 0` | `0003_catalog.py:38-52`; `models/catalog.py:32-45` | Khớp; defaults chỉ ở application |
| `products` (`database-schema.md:38-42`) | `id uuid`; `category_id uuid`; `sku varchar(80)`; `slug varchar(180)`; `name varchar(240)`; `description text?`; `price bigint`; `sale_price bigint?`; `is_active bool app=true`; `published_at timestamptz?`; `deleted_at timestamptz?`; timestamps | FK category restrict; unique SKU/slug; CHECK `price >= 0`; CHECK sale null hoặc `0 < sale_price < price`; index category; index `(category_id,is_active)` | `0003_catalog.py:92-124`; `models/catalog.py:48-86` | Khớp một phần: câu “`price`, `sale_price` nullable” ở dòng 41 mơ hồ/sai với DB; chỉ `sale_price` nullable, `price` bắt buộc |
| `product_images` (`database-schema.md:44-48`) | `id uuid`; `product_id uuid`; `file_path varchar(500)`; `alt_text varchar(255)?`; `sort_order int app=0`; `is_primary bool app=false`; timestamps | FK product cascade; CHECK sort non-negative; index `(product_id,sort_order)`; unique partial `(product_id) WHERE is_primary` | `0003_catalog.py:126-157`; `models/catalog.py:89-112` | Khớp; defaults chỉ ở application |
| `colors` (`database-schema.md:50-52`) | `id uuid`; `name varchar(100)`; `slug varchar(120)`; `hex_code varchar(7)?`; `is_active bool app=true`; timestamps | unique slug | `0003_catalog.py:54-64`; `models/catalog.py:115-124` | Khớp |
| `sizes` (`database-schema.md:54-56`) | `id uuid`; `code varchar(20)`; `name varchar(100)`; `sort_order int app=0`; `is_active bool app=true`; timestamps | unique code; CHECK sort non-negative | `0003_catalog.py:66-77`; `models/catalog.py:127-139` | Khớp một phần: DB không CHECK allow-list `S|M|L|XL|XXL`; danh sách là yêu cầu seed/application |
| `product_variants` (`database-schema.md:58-63`) | `id uuid`; 3 FK UUID; `variant_sku varchar(100)`; `stock_quantity int app=0`; `is_active bool app=true`; `version int app=1`; timestamps | FK product cascade, color/size restrict; unique SKU; unique product/color/size; CHECK stock ≥ 0, version > 0; hai index đúng contract | `0003_catalog.py:159-210`; `models/catalog.py:142-172` | Khớp; defaults chỉ ở application |
| `labels` + `product_labels` (`database-schema.md:65-68`) | label: UUID, `code varchar(40)`, `display_name varchar(100)`, timestamps; join: 2 UUID NOT NULL | label code unique + CHECK `new|best_seller|sale`; composite PK join và 2 FK cascade | `0003_catalog.py:79-90,212-231`; `models/catalog.py:175-203` | Khớp; composite PK đã bảo đảm uniqueness join |
| `knowledge_documents` (`database-schema.md:131-134`) | UUID; `document_type varchar(40)`; `title varchar(240)`; `content text`; `locale varchar(10) app=vi`; `is_active bool app=true`; `version int app=1`; `checksum varchar(64)`; timestamps | CHECK 6 document types; CHECK version > 0; index `(document_type,is_active)` | `0004_rag_content.py:38-63`; `models/knowledge.py:61-84` | Khớp một phần: “locale mặc định vi” là application default, raw SQL bắt buộc truyền |
| `rag_documents` (`database-schema.md:136-142`) | UUID; `source_type varchar(20)`; `source_id uuid`; `title varchar(240)`; `content_for_embedding text`; `source_version int`; `checksum varchar(64)`; `index_status varchar(20) app=pending`; `is_active bool app=true`; timestamps | CHECK source type/status/version; unique source pair; index `(index_status,is_active)`; cố ý không FK polymorphic | `0004_rag_content.py:65-97`; `models/knowledge.py:87-110` | Khớp; status/active không có server default |
| `rag_chunks` (`database-schema.md:144-151`) | UUID; `rag_document_id uuid`; `chunk_index int`; `content text`; `metadata jsonb db={}`; `embedding vector(768)`; `embedding_model varchar(120)`; `source_version int`; `is_active bool app=true`; timestamps | FK cascade; CHECK chunk ≥ 0/version > 0; unique document/version/index; document-active btree; HNSW cosine; GIN `to_tsvector('simple',content)` | `0005_rag_chunks.py:31-92`; `models/knowledge.py:113-155` | Khớp; dimension bị khóa 768 ở migration và config validator |
| `rag_index_jobs` (`database-schema.md:153-160`) | UUID; `source_type varchar(20)`; `source_id uuid`; `source_version int`; `event_type varchar(20) app=upsert`; `payload jsonb db={}`; `payload_version int app=1`; `status varchar(20) app=pending`; `attempt_count int app=0`; `available_at timestamptz app=now`; `locked_at timestamptz?`; `last_error text?`; timestamps | CHECK allow-list và số không âm/dương; unique source/version; claim index `(status,available_at,created_at)`; recovery index `(status,locked_at)`; không FK polymorphic | `0004_rag_content.py:99-159`; `models/knowledge.py:158-210` | Khớp một phần: chỉ `payload` và timestamps có server default; các default vòng đời còn lại do application cung cấp |

PostgreSQL dùng `varchar/text + CHECK`, không tạo PostgreSQL enum riêng. Điều này khớp
lựa chọn được cho phép tại `docs/database-schema.md:9`.

## 4. Phần contract chưa có schema/seed hỗ trợ

| Mô tả contract | Bằng chứng tài liệu | Bằng chứng repository hiện tại | Mức độ | Nội dung cần làm ở task sở hữu |
|---|---|---|---|---|
| Cart/pricing: `carts`, `cart_items`, `coupons`, `coupon_redemptions`, `system_settings` | `docs/database-schema.md:72-100` | Không có migration/model cho các bảng này; migration integration chỉ kỳ vọng 16 bảng tại `test_postgres_migrations.py:54-71` | Chưa hỗ trợ | BE-08/09 phải bổ sung migration + ORM + test; hiện chưa thể enforce owner mode, coupon checks/defaults |
| Order/inventory: `orders`, `order_items`, `inventory_movements` | `database-schema.md:102-127` | Không có migration/model | Chưa hỗ trợ | BE-10/11 phải bổ sung enum/check/index/FK/idempotency; schema hiện tại chưa thể hỗ trợ checkout/order history/stock audit |
| Chat/support: 4 bảng chat và `support_tickets` | `database-schema.md:162-184` | Không có migration/model | Chưa hỗ trợ | BE-16 phải bổ sung token ownership, idempotency, status, source indexes |
| `audit_logs` | `database-schema.md:186-191` | Không có migration/model | Chưa hỗ trợ (tùy chọn) | Chỉ triển khai nếu task điều phối kích hoạt phạm vi tùy chọn |
| Seed đúng 100 sản phẩm, content và demo users | `request.md:115-121,164-167`; `database-schema.md:210-217` | Không có file có tên/pattern `seed`; `README.md:74-76` nói rõ seed chờ BE-06; Compose không chạy seed ngầm | Chưa hỗ trợ, blocker cho BOOT-04..06 | BE-06 phải cung cấp command, deterministic data, verifier, reset và demo credential an toàn |
| Media storage local | `architecture.md:81`; `architecture.md:134` | `.env.example:43-44` có biến dự kiến nhưng Compose không truyền/mount media volume; không có migration liên quan | Chưa hỗ trợ | BE-14/Compose task phải cấu hình mount và runtime settings; không suy ra media đã persistent từ env placeholder |

Do đó các hành vi checkout, coupon, order, inventory audit, chat persistence và support
handoff được mô tả trong tài liệu **chưa được schema hiện tại hỗ trợ**. Đây là khoảng
trống implementation đã được phân công trong `docs/task-breakdown.md`, không phải lý
do để thay đổi contract trong lần rà soát này.

## 5. Ma trận cấu hình dữ liệu và lưu trữ

| Tài liệu/biến | Runtime thực tế | Bằng chứng | Mức độ và nội dung cần sửa |
|---|---|---|---|
| `DATABASE_URL` bắt buộc | `PostgresDsn`, không default; Alembic và SQLAlchemy cùng dùng giá trị này | `config.py:11-12`; `alembic/env.py:8-16`; `db/session.py:5-9`; Compose `:27,65-66,88` | Khớp |
| PostgreSQL/pgvector persistent local | image `pgvector/pgvector:pg16`, port chỉ bind loopback, named volume `postgres_data` | `docker-compose.yml:2-18,142-143` | Khớp |
| `APP_SECRET_KEY`, `APP_ENV`, CORS | secret và DB URL bắt buộc; env development/test/production; production yêu cầu secure cookie | `config.py:8-18,40-45`; `.env.example:1-8` | Khớp |
| `ACCESS_TOKEN_TTL_MINUTES`, `REFRESH_TOKEN_TTL_DAYS` trong kiến trúc | Không tồn tại trong `Settings`; auth dùng opaque cookie/session và `AUTH_SESSION_TTL_DAYS` | `architecture.md:130-132`; `config.py:15`; `auth.py:103-123`; `.env.example:6` | Khớp một phần: architecture dùng tên dự kiến đã lỗi thời; nên trỏ sang `AUTH_SESSION_TTL_DAYS` và cookie-session design |
| `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_EMBEDDING_MODEL` | Có placeholder trong `.env.example` nhưng `Settings.rag_embedding_provider` chỉ chấp nhận `stub`; Compose không truyền ba biến Gemini vào worker | `.env.example:25-30`; `config.py:23-24`; `docker-compose.yml:85-99` | Chưa hỗ trợ Gemini runtime; tài liệu kiến trúc là mục tiêu tương lai, không được coi placeholder là wiring hoạt động |
| `EMBEDDING_DIMENSION=768` | default 768, phải đúng 768; migration là `vector(768)` | `config.py:24,44-45`; `.env.example:30`; `0005_rag_chunks.py:44`; `backend/README.md:113-114` | Khớp |
| Worker timeout/retry/poll/health | defaults `300/120/5/5/300/2/150`; validator yêu cầu poll < health < lease, provider < health | `config.py:25-31,46-76`; `.env.example:31-38`; Compose `:92-99` | Khớp; `RAG_WORKER_STOP_GRACE_PERIOD` là biến Compose-only tại `docker-compose.yml:115`, không phải `Settings` |
| Shipping/media vars | Chỉ có placeholder trong `.env.example`; không có field `Settings`, không truyền vào API Compose | `architecture.md:133-135`; `.env.example:40-44`; toàn bộ `config.py:8-32` | Chưa hỗ trợ; BE-09/14 phải wire và validate trước khi tài liệu gọi là runtime config |
| Migration test URL | `MIGRATION_DATABASE_URL` chỉ bật test PostgreSQL, Compose gán cùng URL test | `test_postgres_migrations.py:14-18`; `docker-compose.yml:62-67` | Khớp |

## 6. Parity ORM ↔ migration và default

| Kiểm tra | Kết quả | Bằng chứng / rủi ro |
|---|---|---|
| Metadata tập trung và naming convention | Khớp | `backend/app/db/base.py:4-22`; test tại `test_database_foundation.py:9-69` |
| Autogenerate drift | `alembic check` trả `No new upgrade operations detected` trên DB mới | Có cảnh báo SQLAlchemy không introspect được type `vector`; vì vậy kết quả này phải đọc cùng test PostgreSQL kiểm tra `vector(768)` và index, không dùng riêng nó làm bằng chứng vector parity |
| Vector/index parity | Khớp | `0005_rag_chunks.py:44,80-92`; `models/knowledge.py:125-152`; PostgreSQL test `test_rag_index_postgres.py::test_postgres_rag_chunk_indexes_match_contract` |
| Application default và server default | Khớp về ORM path, không tương đương raw SQL | Migration chỉ có server defaults cho timestamps và hai JSONB `{}`. UUID, bool, role/status/version/counters/`available_at` phần lớn là application defaults; raw SQL phải truyền giá trị |
| `updated_at` | Khớp trên ORM update, không tự động ở DB | `TimestampMixin` dùng `onupdate=func.now()` nhưng migration chỉ `server_default=now()`; bulk/raw SQL phải tự set `updated_at` |
| Email lowercase | Khớp trên API path, không enforce toàn DB | `schemas/auth.py:13-16,28-31,37-40`; unique index `users.email` không phải functional `lower(email)`/CITEXT |

## 7. Bằng chứng kiểm chứng thực tế

Đã chạy trên PostgreSQL/pgvector mới, project Compose cô lập
`shop-schema-audit`:

```text
docker compose --env-file .env.example \
  --project-name shop-schema-audit --profile test \
  run --rm --build migration-test
# 6 passed in 2.26s

docker compose --env-file .env.example \
  --project-name shop-schema-audit --profile test \
  run --rm migration-test alembic check
# No new upgrade operations detected.
# SAWarning: Did not recognize type 'vector' of column 'embedding'.
```

Đồng thời đã truy vấn `information_schema.columns`, `pg_constraint` và `pg_indexes`
trên database vừa migrate để xác nhận type, nullability, server default,
constraint và index trong mục 3. Database audit phải được dọn bằng:

```bash
docker compose --env-file .env.example \
  --project-name shop-schema-audit --profile test \
  down --volumes --remove-orphans
```

## 8. Kết luận

Schema hiện tại đủ và nhất quán cho foundation, identity/auth, catalog, knowledge,
outbox và RAG chunks. Một Alembic head duy nhất, fresh migration và PostgreSQL tests
đều pass. Các khác biệt cần giữ rõ trong tài liệu là:

1. `docs/database-schema.md` là target schema, không phải danh sách bảng đã deploy;
2. `products.price` bắt buộc, chỉ `sale_price` nullable;
3. `locale=vi` và đa số role/status/bool/version là application default, không phải
   server default;
4. lowercase email chỉ được enforce qua API path;
5. cart/pricing/order/inventory/chat/support, seed và media persistence chưa có;
6. tên TTL auth trong architecture đã lỗi thời, còn Gemini/shipping/media mới chỉ
   là placeholder chưa được runtime wire;
7. hai báo cáo RAG còn đoạn trạng thái branch cũ dù contract RAG vẫn khớp.

Không có schema, public API hoặc event contract nào được thay đổi trong lần đối
chiếu này.
