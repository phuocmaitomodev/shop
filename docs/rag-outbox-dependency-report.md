# Báo cáo dependency cho worker outbox RAG

## Kết luận

**READY có điều kiện tích hợp.** Contract nội bộ cần cho worker đã được chốt bởi tài liệu nguồn sự thật, migration BE-15 đã được duyệt, và điều phối đã khóa embedding ở `gemini-embedding-001` với `EMBEDDING_DIMENSION=768`. Worker không cần và không được đổi public API/event contract.

Điều kiện bắt buộc trước khi triển khai/chạy worker trên một branch:

1. Tích hợp các commit đã duyệt theo dependency của branch đích: BE-03-GAP `25bf834b81654e9939c4e770eafaf5e54267447c`, BE-04-GAP `b294be04b68021b3622b1e814833dd663a0658cf`, rồi BE-15 `9e94856739c71e489ccc6b9ab5017e5650c9fd0a` hoặc các commit tích hợp tương đương đã chứa đầy đủ thay đổi đó.
2. Giữ Alembic thành một chuỗi duy nhất. `0004_rag_content` hiện nối từ `0003_catalog`; nếu branch đích có migration sibling mang cùng vị trí/thứ tự thì phải đổi revision/down-revision khi tích hợp, không tạo nhiều head.
3. Migration chunk phải dùng `vector(768)`. Runtime phải fail-fast nếu `EMBEDDING_DIMENSION != 768`; đổi dimension yêu cầu migration mới và full reindex.
4. Provider stub phải chạy không cần secret. Gemini chỉ được bật khi có key; model lấy từ môi trường và phải hỗ trợ `outputDimensionality=768`.

`RAG-11` và `RAG-12` trong báo cáo này là acceptance IDs tại `docs/acceptance-test.md`, không phải task `RAG-11` (README vận hành) trong `docs/task-breakdown.md`.

## Bằng chứng dependency

| Dependency | Trạng thái | Bằng chứng và ảnh hưởng đến worker |
|---|---|---|
| BE-03 | Hoàn thành qua gap đã duyệt | Commit `25bf834b81654e9939c4e770eafaf5e54267447c` bổ sung CI và migration test trên PostgreSQL/pgvector mới. Handoff ghi fresh Alembic upgrade pass, backend 39 pass + 1 expected skip. Worker được phép dựa vào Alembic/PostgreSQL thực thay vì SQLite metadata. |
| BE-04 | Hoàn thành qua gap đã duyệt | Commit `b294be04b68021b3622b1e814833dd663a0658cf`; review ghi 25 auth/OpenAPI tests pass và không có migration/config impact. RBAC/admin prerequisite đã sẵn sàng cho producer/admin task, dù bản thân consumer không phụ thuộc auth trong vòng claim. |
| BE-15 schema/outbox | Hoàn thành phần producer schema | Commit `9e94856739c71e489ccc6b9ab5017e5650c9fd0a` tạo `knowledge_documents`, `rag_documents`, `rag_index_jobs` và model/test tương ứng. `rag_chunks` được chủ ý để worker migration bổ sung sau khi khóa dimension. |
| pgvector | Sẵn sàng | `backend/alembic/versions/0001_enable_pgvector.py` chạy `CREATE EXTENSION IF NOT EXISTS vector`; Compose dùng `pgvector/pgvector:pg16`. Đây là prerequisite, không tự nó chứng minh pipeline indexing. |
| Embedding decision | Đã khóa | Quyết định điều phối trên task gốc: `GEMINI_EMBEDDING_MODEL=gemini-embedding-001`, `EMBEDDING_DIMENSION=768`, L2-normalize vector 768 chiều; provider stub là default; đổi dimension cần migration + full reindex. |
| Public API | Không đổi | `docs/api-contract.md` chỉ yêu cầu product/knowledge mutation trả `index_status` và admin có reindex/job endpoints. Consumer giao tiếp qua DB/outbox nội bộ, không thêm hoặc đổi endpoint/response trong task worker. |

Branch audit hiện tại chưa chứa ba commit gap/BE-15 nói trên; đó là trạng thái tích hợp Git, không phải thiếu quyết định contract. Worker branch phải đưa đúng commit đã duyệt vào trước khi chạy migration/test.

## Contract dữ liệu nội bộ đã chốt

### Aggregate và version

- `source_type`: allow-list `product | knowledge`.
- `source_id`: UUID ổn định của aggregate nguồn; identity logic là `(source_type, source_id)`.
- `source_version`: số nguyên dương, tăng đơn điệu trên mọi thay đổi làm thay đổi semantic content **hoặc active state**. Worker không tự sinh version.
- `rag_documents`: đúng một projection hiện hành cho `(source_type, source_id)`; chứa `title`, `content_for_embedding`, `source_version`, `checksum`, `index_status`, `is_active`.
- `rag_index_jobs.id`: identity của delivery/job. Unique `(source_type, source_id, source_version)` là idempotency key nghiệp vụ; vì unique không chứa `event_type`, producer phải tăng version khi chuyển active/archive/delete.
- Producer phải ghi source, projection `rag_documents` và job trong cùng transaction. `payload` không phải nguồn nội dung; worker luôn đọc projection hiện hành rồi đối chiếu `source_version`.

### Event envelope

Bảng `rag_index_jobs` là durable outbox và cũng là hàng đợi nội bộ:

- Routing: `id`, `source_type`, `source_id`, `source_version`.
- Operation: `event_type = upsert | delete`.
- Compatibility: `payload_version = 1`; consumer phải fail permanent với version không hỗ trợ, không đoán schema.
- Metadata: `payload jsonb`, mặc định `{}`; chỉ chứa metadata ổn định phục vụ routing/audit, không chứa nội dung canonical hoặc secret.
- Lifecycle: `status = pending | processing | succeeded | failed`.
- Claim/retry/recovery: `attempt_count`, `available_at`, `locked_at`, `last_error`, `created_at`, `updated_at`.

### Ma trận event

| Thay đổi nguồn | Version producer | Event outbox | Projection trước commit | Hành vi worker | Kết quả retrieval |
|---|---:|---|---|---|---|
| Create active | Khởi tạo `1` | `upsert` | Upsert `rag_documents`, `pending`, `is_active=true` | Normalize/chunk/embed; atomically thay chunks của document; đánh dấu document `indexed`, job `succeeded` | Version 1 active sau khi swap hoàn tất |
| Update semantic content | Tăng `+1` | `upsert` | Cập nhật title/content/checksum/version, `pending` | Nếu job cũ thấy version lệch thì no-op `succeeded` (superseded); job mới embed và swap atomically | Chỉ version mới active; không trộn chunks hai version |
| Delete hard source | Tăng `+1` trước khi bỏ source hoặc giữ tombstone projection | `delete` | Projection mang version delete; có thể inactive | Không gọi embedding; xóa/deactivate toàn bộ chunks của projection; document inactive; job `succeeded`. Source đã mất + delete vẫn là success idempotent | Source không còn truy xuất; không còn embedding mồ côi |
| Archive/disable/soft-delete | Tăng `+1` | `delete` | Source/projection còn tồn tại nhưng `is_active=false` hoặc được chuyển inactive trong transaction | Cùng semantics với delete: remove/deactivate chunks; không embed | Source inactive bị loại khỏi retrieval |
| Restore/reactivate | Tăng `+1` | `upsert` | Projection active, content/checksum/version mới, `pending` | Embed lại và atomic swap | Chỉ version restore active |
| Duplicate delivery cùng job | Không đổi | Cùng `id`/idempotency key | Không đổi | `succeeded` không được claim lại; gọi xử lý lặp là no-op; unique key chặn job trùng | Không nhân đôi chunk/side effect |
| Event cũ đến sau event mới | Version nhỏ hơn projection | `upsert` hoặc `delete` | Projection đang ở version mới hơn | Đánh dấu job cũ `succeeded`/superseded; tuyệt đối không xóa hoặc ghi đè version mới | Version mới giữ nguyên |

Create/update dùng chung `upsert`; delete/archive dùng chung `delete`. Đây là mapping nội bộ, không mở rộng allow-list event hiện có.

## Claim, retry, lỗi và recovery

1. Trong một transaction ngắn, recovery chuyển job `processing` có `locked_at` quá timeout về `pending`.
2. Claim chọn job `pending AND available_at <= now` theo `created_at, id`, dùng `SELECT ... FOR UPDATE SKIP LOCKED`, chuyển `processing`, đặt `locked_at`, tăng `attempt_count`, rồi commit **trước** khi gọi provider.
3. Thành công hoặc version superseded: `succeeded`, xóa `locked_at`; swap chunks + trạng thái document/job phải nằm trong một transaction.
4. Lỗi retryable (timeout, 429, 5xx, provider/network tạm thời): về `pending`, đặt `available_at` theo exponential backoff hữu hạn, xóa lock.
5. Lỗi permanent (payload version, dimension/model/response invalid, source upsert không tồn tại) hoặc hết `max_attempts`: job `failed`; document cùng version `failed` nếu tồn tại.
6. `last_error` phải loại control characters, giới hạn độ dài, không ghi API key, cookie, token, raw response nhạy cảm hay stack trace chứa secret.
7. Một lease chỉ hợp lệ đến `locked_at + lock_timeout`. Timeout phải lớn hơn provider timeout/batch worst-case; xử lý phải idempotent vì process cũ có thể quay lại sau khi lease hết hạn.

Indexes tối thiểu của outbox:

- Claim: `(status, available_at, created_at)`.
- Recovery: `(status, locked_at)`.
- Idempotency: unique `(source_type, source_id, source_version)`.

## Schema chunk và abstraction embedding

Migration worker được phép bổ sung `rag_chunks` đúng contract:

- FK `rag_document_id -> rag_documents.id ON DELETE CASCADE`.
- `chunk_index >= 0`, `content`, `metadata jsonb`, `embedding vector(768)`, `embedding_model`, `source_version > 0`, `is_active`, timestamps.
- Unique `(rag_document_id, source_version, chunk_index)`.
- Index `(rag_document_id, is_active)`.
- HNSW cosine trên `embedding` và GIN FTS trên `to_tsvector('simple', content)`.

Boundary provider nội bộ:

```text
EmbeddingProvider.model_name: str
EmbeddingProvider.embed(texts: Sequence[str]) -> list[list[float]]
```

Mọi implementation phải:

- bảo toàn thứ tự và số lượng vector so với input;
- xác nhận đúng 768 phần tử, giá trị finite, magnitude khác 0;
- L2-normalize trước khi lưu/tính cosine;
- phân loại lỗi thành retryable và permanent;
- không log secret;
- có stub deterministic chạy offline và Gemini adapter cấu hình qua môi trường.

## Ràng buộc acceptance RAG-11/RAG-12

### RAG-11 — product reindex

- Product create/update phải tạo projection/job cùng transaction; mô tả semantic mới chỉ trở thành active sau atomic swap.
- Product facts động (giá, sale, promotion hiện hành, màu, size, stock, ảnh/link) không được lấy từ chunk/vector; retrieval chỉ trả candidate ID rồi hydrate lại SQL tại request time.
- Product delete/archive tạo `delete` với version tăng; event cũ không được xóa index version mới.
- Test phải chứng minh update description làm semantic retrieval dùng nội dung mới, retry thành công, stale event/duplicate không tạo side effect lặp, và field động vẫn khớp SQL.

### RAG-12 — knowledge reindex

- Knowledge create/update tăng `knowledge_documents.version`, cập nhật checksum/projection và tạo job atomically.
- Version mới chỉ được retrieval sau khi chunks đã index thành công; swap không để trộn chunks cũ/mới.
- Document inactive/archive/delete phải bị loại khỏi vector lẫn keyword retrieval và không để orphan chunks.
- Test phải chứng minh version mới truy xuất được, version cũ/inactive không truy xuất được, provider failure giữ trạng thái có thể quan sát/retry, và permanent failure đi tới `failed`.

Cả hai acceptance cần PostgreSQL/pgvector thật cho migration, vector index và concurrent claim; test SQLite chỉ phù hợp cho state machine/unit behavior.

## Lệnh kiểm chứng bắt buộc cho task sau

Chạy trên branch đã tích hợp dependency, với placeholder an toàn và không cần Gemini key thật:

```bash
git diff --check
docker compose --env-file .env.example config --quiet
docker build --target test -t shop-backend-rag-test backend
docker run --rm shop-backend-rag-test pytest -W error -q \
  tests/test_config.py \
  tests/test_database_foundation.py \
  tests/test_knowledge_models.py \
  tests/test_rag_index_worker.py
```

Ngoài unit tests, dùng PostgreSQL/pgvector cô lập để chạy:

```bash
alembic upgrade head
pytest -W error -q tests/test_rag_index_postgres.py
alembic heads
```

Oracle tối thiểu:

- đúng một Alembic head;
- `vector(768)`, HNSW cosine, FTS GIN, unique/version indexes tồn tại;
- hai worker không claim cùng job có lease hợp lệ;
- stale `processing` được reclaim;
- transient retry/backoff, permanent/exhausted failure, duplicate no-op, stale delete protection và atomic version swap đều pass;
- provider stub pass không cần key; Gemini smoke là optional và chỉ chạy khi operator cấp secret ngoài repository.

## Rủi ro tích hợp còn lại

- Các commit BE-03-GAP, BE-04-GAP và BE-15 đang ở task branches/commits riêng; owner/orchestrator chưa merge. Downstream không được suy ra rằng branch hiện tại đã có chúng.
- Migration `0004_rag_content` có thể va chạm revision/order với migration sibling của các backend task khác; phải serialize trước khi merge.
- `rag_chunks` và worker là implementation downstream, không phải bằng chứng BE-15 hiện đã chứa pipeline hoàn chỉnh.
- RAG-11/RAG-12 chỉ có thể đánh dấu PASS sau retrieval/freshness tests end-to-end; schema hoặc state-machine test riêng không đủ.