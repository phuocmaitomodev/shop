# Ma trận bằng chứng migration, schema, seed và RAG

## 1. Phạm vi, baseline và quy ước

Đây là ma trận bằng chứng hợp nhất duy nhất cho migration/ORM/seed, clean-room
bootstrap, lưu trữ và runtime RAG trên tree hiện tại. Tài liệu chỉ ghi nhận hiện
trạng và đề xuất sửa **tài liệu** hoặc issue; nó không thay đổi schema, migration,
public API hay event contract. `docs/database-schema.md` vẫn là schema mục tiêu,
không phải danh sách bảng đã deploy.

Nguồn đã đối chiếu: `request.md`; `README.md`; `backend/README.md`;
`.env.example`; `docker-compose.yml`; `docs/database-schema.md`;
`docs/architecture.md`; `docs/rag-design.md`; toàn bộ
`backend/alembic/versions/*.py`, `backend/app/models/*.py`,
`backend/app/rag/*.py`, `backend/app/api/v1/*.py`, cấu hình và test liên quan.

Baseline bằng chứng thực thi:

- audit migration/schema ở commit `6007f824b7707d0f22a9f796095c732912d8bf13`;
- clean-room bootstrap ở baseline `4f56f53541853370832ddbd035aefd19eb3adb56`;
- audit RAG ở commit `258cb53112794d1223bf325d408eab3419ea5c5e`;
- tree hợp nhất hiện tại đã được xác minh lại theo mục 6; release sau này vẫn
  phải chạy lại các gate trên checkout sẽ phát hành.

Chỉ dùng năm trạng thái sau:

- **Khớp**: tài liệu và implementation/runtime cùng xác nhận.
- **Khớp một phần**: có implementation nhưng default, enforcement, wiring hoặc
  phạm vi khác cách tài liệu diễn đạt.
- **Không khớp**: tài liệu mô tả năng lực/cấu hình hiện hành nhưng repository
  hiện không cung cấp đúng hành vi đó.
- **Không có bằng chứng**: contract mục tiêu có mô tả nhưng không tìm thấy
  migration/model/runtime/test tương ứng; không được tính là đã triển khai.
- **Không áp dụng**: hạng mục có chủ ý không phải database invariant hoặc nằm
  ngoài phạm vi bắt buộc; lý do phải được ghi rõ.

Trong cột “Thực tế”: `?` là nullable; `db=` là server default; `app=` là
default Python/ORM. UUID primary key có `app=uuid4`, không có database default.
Các bảng dùng `TimestampMixin` có `created_at timestamptz db=now()` và
`updated_at timestamptz db=now(), app-on-update=now()`; không có trigger DB tự
cập nhật `updated_at`.

## 2. Ma trận bằng chứng hợp nhất

| ID | Hạng mục/tài liệu | Thực tế migration, ORM hoặc runtime | Bằng chứng repository | Trạng thái | Sửa tài liệu/issue và ảnh hưởng |
|---|---|---|---|---|---|
| MIG-01 | Lệnh upgrade `docker compose exec api alembic upgrade head` | URL lấy từ `Settings.database_url`; API không tự migrate | `README.md:10-15`; `backend/alembic/env.py:8-16,19-59`; `docker-compose.yml:20-55` | Khớp | Giữ lệnh thủ công; ảnh hưởng cao nếu mô tả thành auto-migrate vì worker có thể chạy trước schema |
| MIG-02 | Một Alembic head | Head `0005_rag_chunks`; chuỗi `0001` → `0005` liên tục | `backend/tests/test_database_foundation.py:72-92`; năm revision `revision/down_revision` | Khớp | Không sửa; gate tích hợp phải tiếp tục kiểm tra single head |
| MIG-03 | Fresh PostgreSQL/pgvector lane | DB phải trống, upgrade head, kiểm tra extension/revision/16 bảng và worker/index semantics | `docker-compose.yml:57-78`; `backend/tests/integration/test_postgres_migrations.py:46-97`; `backend/tests/test_rag_index_postgres.py` | Khớp | Luôn cleanup volume; ảnh hưởng cao nếu tái dùng DB vì test sẽ không còn chứng minh clean migration |
| MIG-04 | Migration order mục tiêu gồm cart/order/chat | Chuỗi hiện tại là extension → identity → catalog → knowledge/outbox → chunks/index; bỏ qua phase chưa triển khai | `docs/database-schema.md:206-208`; `backend/alembic/versions/0001_enable_pgvector.py:12-23`; `0002_identity_auth.py:14-121`; `0003_catalog.py:14-254`; `0004_rag_content.py:14-171`; `0005_rag_chunks.py:15-99` | Khớp một phần | Ghi rõ đây là thứ tự mục tiêu; ảnh hưởng cao vì đọc nhầm thành schema đã deploy |
| MIG-05 | Downgrade/reset | Cả năm revision có `downgrade()`; clean-room upgrade → downgrade base → upgrade pass; reset công bố bằng `down --volumes` | `0001_enable_pgvector.py:22`; `0002_identity_auth.py:113`; `0003_catalog.py:234`; `0004_rag_content.py:162`; `0005_rag_chunks.py:95`; `README.md:68-72` | Khớp một phần | Nếu công bố downgrade, thêm cảnh báo phá hủy dữ liệu; nếu không, chỉ hỗ trợ reset volume. Ảnh hưởng cao với dữ liệu local |
| MIG-06 | Bootstrap Compose | `up` có thể đánh dấu API ready bằng `SELECT 1` và worker retry lỗi trước migration; sau migration bốn service healthy | `README.md:10-15`; `docker-compose.yml:40-55,99-115,125-140`; `backend/app/api/v1/health.py:23-36` | Không khớp | Sửa runbook/order hoặc tạo migration gate; ảnh hưởng cao: false-ready và log lỗi lặp |
| DB-01 | `users` | `id uuid`; `email varchar(320)`; `password_hash varchar(255)`; `full_name varchar(200)`; `phone?`; role `customer`, `admin` với `app=customer`; `is_active app=true`; unique email, role CHECK | `docs/database-schema.md:15-19`; `0002_identity_auth.py:21-47`; `backend/app/models/auth.py:18-36`; `backend/app/schemas/auth.py:13-16` | Khớp một phần | Ghi lowercase là API enforcement, unique DB case-sensitive; role/active không có server default. Ảnh hưởng trung bình cho raw SQL/import |
| DB-02 | `auth_sessions` | UUIDs, token hash, expiry, revoked/user-agent nullable; FK cascade; unique hash; user và `(user_id,expires_at)` indexes | `docs/database-schema.md:21-24`; `0002_identity_auth.py:49-79`; `backend/app/models/auth.py:46-66` | Khớp | Không sửa; metadata thực tế là `user_agent` |
| DB-03 | `password_reset_tokens` | UUIDs, hash, expiry, `used_at?`, created; FK cascade; unique hash; user index | `docs/database-schema.md:26-29`; `0002_identity_auth.py:81-110`; `backend/app/models/auth.py:69-83` | Khớp | Không sửa |
| DB-04 | `categories` | UUID, name/slug, description?, sort/app=0, active/app=true, timestamps; unique slug; sort ≥ 0 | `docs/database-schema.md:33-36`; `0003_catalog.py:38-52`; `backend/app/models/catalog.py:32-45` | Khớp | Nêu defaults là application nếu tài liệu cần raw-SQL semantics; ảnh hưởng thấp |
| DB-05 | `products` | `price bigint NOT NULL`; `sale_price bigint?`; category FK restrict; unique SKU/slug; non-negative price; sale `0 < sale < price`; indexes category và category/active | `docs/database-schema.md:38-42`; `0003_catalog.py:92-124`; `backend/app/models/catalog.py:48-86` | Khớp một phần | Sửa câu “price, sale_price nullable” thành chỉ sale nullable; ảnh hưởng cao cho contract nhập dữ liệu |
| DB-06 | `product_images` | Path 500, alt?; sort/app=0, primary/app=false; FK cascade; sort ≥ 0; order index; unique partial primary/product | `docs/database-schema.md:44-48`; `0003_catalog.py:126-157`; `backend/app/models/catalog.py:89-112` | Khớp | Nêu defaults application nếu cần; ảnh hưởng thấp |
| DB-07 | `colors` | Name/slug/hex?; active/app=true; unique slug | `docs/database-schema.md:50-52`; `0003_catalog.py:54-64`; `backend/app/models/catalog.py:115-124` | Khớp | Không sửa |
| DB-08 | `sizes` | Code/name/sort/active; unique code; sort ≥ 0; không có DB CHECK allow-list size | `docs/database-schema.md:54-56`; `0003_catalog.py:66-77`; `backend/app/models/catalog.py:127-139` | Khớp một phần | Ghi `S..XXL` là seed/application rule; ảnh hưởng trung bình nếu consumer giả định DB từ chối code khác |
| DB-09 | `product_variants` | Ba FK; unique SKU và product/color/size; stock ≥ 0; version > 0; required filter indexes; stock/active/version là application defaults | `docs/database-schema.md:58-63`; `0003_catalog.py:159-210`; `backend/app/models/catalog.py:142-172` | Khớp | Ghi rõ defaults application; ảnh hưởng trung bình cho raw SQL |
| DB-10 | `labels`, `product_labels` | Label code CHECK ba giá trị `new`, `best_seller`, `sale`; unique code; join composite PK và cascade FKs | `docs/database-schema.md:65-68`; `0003_catalog.py:79-90,212-231`; `backend/app/models/catalog.py:175-203` | Khớp | Không sửa |
| DB-11 | `knowledge_documents` | Type varchar + 6-value CHECK; title/content; locale/app=`vi`; active/app=true; version/app=1 + CHECK; checksum; type/active index | `docs/database-schema.md:131-134`; `0004_rag_content.py:38-63`; `backend/app/models/knowledge.py:61-84` | Khớp một phần | Ghi locale/active/version là application defaults; ảnh hưởng cao cho producer raw SQL |
| DB-12 | `rag_documents` | Source type varchar CHECK, polymorphic source UUID không FK; unique source pair; version/status checks; status/active application defaults; status-active index | `docs/database-schema.md:136-142,159-160`; `0004_rag_content.py:65-97`; `backend/app/models/knowledge.py:87-110` | Khớp một phần | Ghi producer/service chịu trách nhiệm referential integrity và defaults; ảnh hưởng cao cho source bị xóa |
| DB-13 | `rag_chunks` | FK cascade; chunk/version checks; unique document/version/index; JSONB `db={}`; `vector(768)`; model/version/active; btree, HNSW cosine và GIN FTS indexes | `docs/database-schema.md:144-151`; `0005_rag_chunks.py:31-92`; `backend/app/models/knowledge.py:113-155` | Khớp | `is_active` vẫn là app default; đổi dimension cần migration + full reindex. Ảnh hưởng cao |
| DB-14 | `rag_index_jobs` | Source/event/status varchar + CHECK; payload JSONB `db={}`; version/count checks; available/locked/error nullability; unique source/version; claim/recovery indexes | `docs/database-schema.md:153-160`; `0004_rag_content.py:99-159`; `backend/app/models/knowledge.py:158-210` | Khớp một phần | Event/payload version/status/count/available là application defaults; ghi producer phải truyền đủ hoặc đi qua ORM. Ảnh hưởng cao cho outbox raw SQL |
| DB-15 | PostgreSQL enum | Không có enum type; dùng varchar/text + CHECK | `docs/database-schema.md:9`; các CHECK trong `0002`–`0004` | Khớp | Không sửa; đây là lựa chọn contract cho phép |
| DB-16 | UUID và timestamps | UUID là app default; created/updated có server `now()`, nhưng updated chỉ tự đổi qua ORM `onupdate` | `backend/app/models/catalog.py:23-29`; timestamp helpers trong `0002`–`0005` | Khớp một phần | Ghi rõ raw/bulk SQL phải cấp UUID và cập nhật timestamp; ảnh hưởng trung bình cho tooling ngoài ORM |
| GAP-01 | Cart/pricing: 5 bảng | Không có migration/model; fresh migration expected-table set không chứa chúng | `docs/database-schema.md:72-100`; `backend/tests/integration/test_postgres_migrations.py:54-71` | Không có bằng chứng | Ghi target-only và mở BE-08/09; ảnh hưởng chặn cart owner, coupon và setting invariants |
| GAP-02 | Order/inventory: 3 bảng | Không có migration/model | `docs/database-schema.md:102-127`; `backend/tests/integration/test_postgres_migrations.py:54-71` | Không có bằng chứng | Ghi target-only và mở BE-10/11; ảnh hưởng chặn checkout, order history, stock audit/idempotency |
| GAP-03 | Chat/support: 4 chat tables + ticket | Không có migration/model/route/expected table | `docs/database-schema.md:162-184`; `backend/app/models/__init__.py:12-30`; `backend/app/api/v1/router.py:1-14`; `test_postgres_migrations.py:54-71` | Không khớp | Architecture/API phải gắn nhãn target; BE-16 phải freeze enum/default/nullability/FK/idempotency/index. Ảnh hưởng chặn session, trace, transcript và handoff |
| GAP-04 | `audit_logs` tùy chọn | Không có migration/model | `docs/database-schema.md:186-191`; `backend/app/models/__init__.py:12-30` | Không áp dụng | Không triển khai nếu điều phối không kích hoạt scope tùy chọn; không ảnh hưởng acceptance bắt buộc hiện tại |
| SEED-01 | Seed đúng 100 sản phẩm/7 nhóm, variants, content và demo users | Không có production seed module/CLI/service; migration mới có 0 product và 0 user | `request.md` mục dữ liệu; `docs/database-schema.md:70,210-217`; `README.md:74-76`; không có tracked file tên/pattern `seed` | Không có bằng chứng | BE-06 phải thêm deterministic command, dữ liệu và verifier; ảnh hưởng chặn BOOT-04/05/06 và demo login |
| SEED-02 | Idempotent hoặc fail rõ, reset + reseed | Reset và migration pass; chưa có seed để chạy lần hai | `docs/database-schema.md:216-217`; `README.md:68-76` | Không có bằng chứng | Không tuyên bố idempotent; ảnh hưởng chặn BOOT-08 |
| CFG-01 | Required Compose env | `POSTGRES_PASSWORD`, `APP_SECRET_KEY`, `DATABASE_URL` fail-fast khi thiếu; DB URL là `PostgresDsn`; CORS là JSON array string | `docker-compose.yml:5-9,24-39,62-69,85-99`; `backend/app/core/config.py:8-14`; `.env.example:1-23` | Khớp | README nên phân nhóm required/default/reserved; ảnh hưởng trung bình cho bootstrap |
| CFG-02 | Auth TTL trong architecture | Runtime dùng opaque session `AUTH_SESSION_TTL_DAYS`; không có access/refresh TTL settings | `docs/architecture.md:98-106,126-137`; `.env.example:6`; `backend/app/core/config.py:15-18` | Không khớp | Sửa architecture trỏ opaque cookie-session; ảnh hưởng trung bình do operator có thể cấu hình biến bị bỏ qua |
| CFG-03 | PostgreSQL persistence | Image pgvector 16, loopback port, named volume | `docker-compose.yml:2-18,142-143` | Khớp | Không sửa; `down --volumes` cố ý xóa dữ liệu |
| CFG-04 | Media storage/config | Env có `MEDIA_ROOT`/`PUBLIC_MEDIA_BASE_URL`; Settings/Compose không đọc/truyền và không mount media | `docs/architecture.md:73-83,126-137`; `.env.example:40-44`; `backend/app/core/config.py:8-31`; `docker-compose.yml:20-55,117-143` | Không khớp | Gắn nhãn reserved hoặc triển khai ở BE-14; ảnh hưởng cao: chưa có persistence/serving contract |
| CFG-05 | Shipping config | Hai biến chỉ là reserved; không có Settings/consumer | `.env.example:40-42`; `docs/architecture.md:126-137`; `backend/app/core/config.py:8-31` | Không khớp | Gắn nhãn target/reserved trong architecture; ảnh hưởng chặn pricing runtime |
| CFG-06 | Embedding dimension | Settings bắt buộc đúng 768; migration/model là vector(768) | `.env.example:30`; `backend/app/core/config.py:24,44-45`; `0005_rag_chunks.py:44`; `backend/app/models/knowledge.py:150-152` | Khớp | Không hard-code model name; đổi dimension cần migration/reindex. Ảnh hưởng cao |
| CFG-07 | Worker lease/retry/poll/health/stop grace | Defaults được wire; validator enforce poll < health < lease, provider < health < lease; stop grace là Compose-only | `.env.example:31-38`; `backend/app/core/config.py:25-31,46-76`; `docker-compose.yml:90-115` | Khớp | Ghi stop grace không phải Pydantic setting; ảnh hưởng thấp |
| CFG-08 | Host port overrides | Đổi API port cần đổi `VITE_API_BASE_URL`; đổi frontend port cần đổi CORS | `.env.example:5,14-16`; `docker-compose.yml:29,38-39,121-124` | Khớp một phần | README phải nêu coupling; ảnh hưởng trung bình: UI lên nhưng API/CORS sai |
| RAG-01 | Knowledge producer + atomic outbox | Create/update/archive/reindex ghi source/projection/job cùng session; event theo active/version | `docs/rag-design.md` phần indexing; `backend/app/api/v1/admin_knowledge.py:156-242,349-452` | Khớp | Giữ transaction/idempotency tests; ảnh hưởng cao nếu tách commit |
| RAG-02 | Claim, lease, fencing, retry, atomic chunk swap | `SKIP LOCKED`, recovery/fencing, validate embedding, delete/replace chunks và finalize trong transaction | `backend/app/rag/worker.py:70-150,179-257,265-354`; `backend/tests/test_rag_index_postgres.py` | Khớp | Không sửa contract; tiếp tục test PostgreSQL thật |
| RAG-03 | Product projection/reindex | Schema cho `source_type=product`, nhưng producer usages chỉ có knowledge/worker/model | `docs/rag-design.md` phần product indexing; `backend/app/models/knowledge.py:34,87-110`; `backend/app/api/v1/admin_knowledge.py` | Không có bằng chứng | RAG-03/product mutation phải tạo projection/job; ảnh hưởng chặn semantic product search |
| RAG-04 | Gemini embedding/generation | `.env.example` có placeholder; Settings chỉ cho `stub`, extra ignored; Compose không truyền Gemini; runner dùng deterministic provider; không có adapter/SDK/generation | `.env.example:25-30`; `backend/app/core/config.py:23,33-38`; `backend/app/rag/provider.py:1-42`; `backend/app/rag/run_worker.py:48-63`; `docker-compose.yml:85-99`; `backend/requirements.txt:1-9` | Không khớp | Architecture/README phải nói target/reserved; RAG adapter task phải wire config/secret/SDK. Ảnh hưởng chặn Gemini acceptance nhưng không chặn local stub |
| RAG-05 | Vector + FTS indexes | DDL HNSW cosine và GIN FTS tồn tại, parity migration/ORM được test | `docs/database-schema.md:144-151`; `0005_rag_chunks.py:80-92`; `backend/app/models/knowledge.py:124-135`; `backend/tests/test_rag_index_postgres.py:109-140` | Khớp | Không suy từ index thành retrieval hoạt động; ảnh hưởng cao đến báo cáo acceptance |
| RAG-06 | Hybrid retrieval/ranking/top-k/threshold | Không có query operator cosine/FTS ranking, retrieval service hoặc config top-k/threshold | `docs/rag-design.md` phần retrieval; `backend/app/core/config.py:8-77`; search production code không có `<=>`, `<#>`, `<->`, `ts_rank`, `plainto_tsquery` | Không có bằng chứng | Mở RAG retrieval issue + PostgreSQL tests; ảnh hưởng chặn RAG-01..15 runtime |
| RAG-07 | SQL hydration dữ liệu động | Không có call path từ vector candidate sang catalog SQL | `AGENTS.md:25,44`; `docs/architecture.md:52-55,118-120`; không có retrieval orchestrator trong `backend/app` | Không có bằng chứng | RAG-04/06 phải batch hydrate giá/sale/màu/size/stock/ảnh; ảnh hưởng cao: không được để model/vector làm nguồn dữ liệu động |
| RAG-08 | Session/message/source trace và support handoff | Thiếu schema/model/API nên không thể lưu context, citation, transcript hoặc ticket | `docs/database-schema.md:162-184`; `docs/api-contract.md:116-140,181-185`; `backend/app/models/__init__.py:12-30`; `backend/app/api/v1/router.py:1-14` | Không khớp | Gắn nhãn target và triển khai BE-16 trước RAG session/handoff; ảnh hưởng chặn persistence, isolation và admin support |

## 3. Model–migration drift cần theo dõi riêng

Không phát hiện drift cấu trúc bắt buộc giữa model và migration cho 16 bảng đang
triển khai. `alembic check` trả “No new upgrade operations detected”, nhưng
SQLAlchemy cảnh báo không introspect được type `vector`; vì vậy phải đọc kết quả
này cùng PostgreSQL integration test cho `vector(768)` và index.

Các khác biệt semantics còn lại:

1. UUID primary key là `default=uuid4` ở ORM, không có server default.
2. `role`, boolean, sort/version/status/count, `locale`, `available_at` và phần
   lớn lifecycle defaults là client-side; migration chỉ có server defaults cho
   timestamps và JSONB `{}` của chunk/job.
3. `updated_at` tự đổi trên ORM path, không tự đổi với raw/bulk SQL.
4. Lowercase email được validator API enforce; DB unique vẫn case-sensitive.
5. `rag_documents.source_id`/`rag_index_jobs.source_id` cố ý polymorphic và không
   có FK; referential integrity thuộc transaction/service.

Đây là **Khớp một phần**, không phải lý do tự ý sửa migration trong audit này.
Task schema sở hữu phải quyết định server-default/DB-invariant hay application-only
và thêm migration nếu contract thay đổi.

## 4. Hành vi được mô tả nhưng schema chưa hỗ trợ

1. Cart ownership, coupon và shipping settings.
2. Checkout/order snapshot, inventory movement và idempotent stock restoration.
3. Chat session/message/source, anonymous token isolation và context state.
4. Citation/retrieval trace gắn assistant message.
5. Support ticket, transcript, assignment và idempotency.
6. Product semantic projection và live SQL hydration.
7. Gemini embedding/generation và hybrid retrieval runtime.

Các mục trên là **Không có bằng chứng** khi mới có target contract, hoặc **Không
khớp** khi architecture/API diễn đạt như năng lực hệ thống hiện hành. Không mục
nào được phép chuyển thành PASS chỉ vì DDL vector/index hoặc placeholder env đã có.

## 5. Sai lệch tài liệu cần chốt

| Ưu tiên | Nội dung tài liệu cần sửa | Ảnh hưởng |
|---|---|---|
| P0 | Đổi bootstrap order để migration/gate hoàn tất trước API/worker được coi ready | Tránh false-ready và worker lỗi lặp trên DB sạch |
| P0 | Đánh dấu cart/order/chat/support/retrieval/Gemini là target/chưa triển khai | Tránh nghiệm thu sai năng lực runtime |
| P0 | Sửa `products.price`: bắt buộc, chỉ `sale_price` nullable | Tránh payload/import sai contract |
| P1 | Phân biệt server default và application default; nêu semantics `updated_at`, UUID và lowercase email | Tránh raw SQL tạo dữ liệu thiếu/sai invariant |
| P1 | Sửa auth TTL architecture sang opaque session và `AUTH_SESSION_TTL_DAYS` | Tránh cấu hình biến không được runtime đọc |
| P1 | Phân loại env required/default/reserved; nêu port coupling | Tránh bootstrap/UI-CORS lỗi khó thấy |
| P1 | Gắn nhãn media/shipping/Gemini placeholders là reserved cho tới khi wire | Tránh hiểu nhầm có persistence/provider thật |
| P1 | Khi BE-06 có seed, thêm command, prerequisite, verifier, demo account an toàn và rerun behavior | Bỏ blocker BOOT-04/05/06/08 |
| P2 | Nếu hỗ trợ downgrade, công bố command + cảnh báo mất dữ liệu; nếu không, chỉ nêu reset volume | Tránh thao tác phá hủy ngoài ý muốn |

## 6. Bằng chứng thực thi và giới hạn

Đã xác minh lại trực tiếp trên checkout hợp nhất này:

```text
docker compose --env-file .env.example config --quiet
# pass

docker build --target test -t shop-e2ab8401-test backend
docker run --rm shop-e2ab8401-test pytest -W error -q \
  tests/test_config.py tests/test_database_foundation.py \
  tests/test_knowledge_models.py tests/test_rag_index_worker.py \
  tests/test_rag_worker_runtime.py
# 36 passed in 3.04s

POSTGRES_PORT=55441 docker compose --env-file .env.example \
  --project-name shop-e2ab8401 --profile test run --rm --build migration-test
# 6 passed in 2.38s; project/volume đã được xóa bằng
# docker compose ... down --volumes --remove-orphans

matrix validator
# 44/44 hàng có đúng 6 cột, trạng thái chuẩn và ít nhất một file:dòng hợp lệ

git diff --check
# pass
```

Các lượt audit cha đã chạy trong Compose project/volume cô lập và cleanup sau
kiểm tra:

```text
docker compose --env-file .env.example config --quiet
# exit 0

docker compose --env-file .env.example --project-name <isolated> \
  --profile test run --rm --build migration-test
# 6 passed (fresh PostgreSQL/pgvector)

docker compose run --rm --build api alembic upgrade head
docker compose run --rm api alembic downgrade base
docker compose run --rm api alembic upgrade head
# pass; 16 public tables + vector restored at head

docker compose --env-file .env.example --project-name <isolated> \
  --profile test run --rm migration-test alembic check
# No new upgrade operations detected; vector introspection warning noted above

docker build --target test -t shop-backend-test backend
docker run --rm shop-backend-test
# 76 passed, 6 expected skips in migration/schema audit

docker run --rm <targeted-backend-image> pytest -W error -q \
  tests/test_config.py tests/test_database_foundation.py \
  tests/test_knowledge_models.py tests/test_rag_index_worker.py \
  tests/test_rag_worker_runtime.py
# 36 passed in RAG audit

docker compose down --volumes --remove-orphans
# temporary containers/networks/volumes removed
```

Giới hạn:

- kết quả chi tiết là snapshot của các baseline nêu ở mục 1; targeted suite và
  fresh PostgreSQL lane đã được chạy lại trên tree hợp nhất như trên;
- suite hiện có chứng minh migration/indexing foundation, không chứng minh
  retrieval, Gemini, chat, support hay seed chưa tồn tại;
- `alembic check` một mình không chứng minh pgvector parity;
- clean-room bootstrap dùng cổng/project/volume riêng và không chạm DB dùng chung;
- không có seed command nên không thể kiểm chứng repeatability/idempotency.

## 7. Tiêu chí nghiệm thu của audit

- [x] Có một ma trận canonical bao phủ command migration, bảng/cột, type,
  nullability, enum/CHECK, FK/unique/index, server/application default, seed,
  storage, env và RAG runtime.
- [x] Mọi hàng có ít nhất một bằng chứng file:dòng hoặc symbol/search scope.
- [x] Trạng thái chỉ dùng năm giá trị chuẩn ở mục 1.
- [x] Mỗi sai lệch có nội dung tài liệu/issue cần sửa và mức ảnh hưởng.
- [x] Có danh sách riêng model–migration drift và hành vi schema chưa hỗ trợ.
- [x] Đề xuất không thay đổi schema, migration, public API hoặc event contract.
- [x] Có command/test thực tế, giới hạn bằng chứng và blocker seed/runtime.

Kết luận: audit tài liệu **đạt** tiêu chí; implementation tổng thể chưa đạt các
acceptance về seed, commerce, retrieval/Gemini, chat và support đã liệt kê.