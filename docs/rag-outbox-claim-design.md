# Thiết kế claim outbox RAG

## Kết luận

**READY, với điều kiện tích hợp bắt buộc.** Dependency report đã được duyệt tại commit `797e7b32341a5a1a8d3e194cf4bfa6b4961d877d`; schema/producer đã được duyệt tại `12d2469d040e7b9a22edb24f6ed3557f3ea712c9` và `b8d780308a66c2e08897d43c50ecc052cf8fc493`; implementation worker tham chiếu hiện có tại `f7c6b7eb55f21723359954a749b16ec96bfed4d4`.

Branch nền `9124d6fc1ceb8a13a336b1b04d12fe513acce9e4` chưa chứa các dependency này. Trước khi chạy worker, branch tích hợp phải chứa BE-03-GAP, BE-04-GAP, BE-15 producer/schema và worker theo một chuỗi Alembic duy nhất. Đây là điều kiện tích hợp, không phải thiếu quyết định contract.

Không thay đổi public API hoặc event contract. Thiết kế dùng đúng `rag_index_jobs` đã quy định trong `docs/database-schema.md` và envelope nội bộ `upsert | delete`, payload version `1` đã được chốt trong dependency report.

## Bằng chứng đã kiểm tra

| Hạng mục | Bằng chứng |
|---|---|
| Contract nguồn | `docs/database-schema.md` quy định `rag_index_jobs.id`, status, `attempt_count`, `available_at`, `locked_at`, `last_error` và unique `(source_type, source_id, source_version)`; `docs/rag-design.md` yêu cầu claim bằng `SKIP LOCKED`, idempotent và retry hữu hạn. |
| Dependency report | `797e7b3:docs/rag-outbox-dependency-report.md` kết luận READY có điều kiện, khóa aggregate/version, event matrix, retry/recovery, `vector(768)` và ranh giới provider. |
| Schema producer | `12d2469:backend/alembic/versions/0004_rag_content.py` tạo outbox với claim index `(status, available_at, created_at)`, recovery index `(status, locked_at)` và unique idempotency. Model tương ứng ở `backend/app/models/knowledge.py` trên commit đó. |
| Producer/API | `b8d7803` ghi source, projection và outbox trong transaction của admin knowledge mutation; review độc lập đã duyệt canonical checksum và 53 tests. |
| Worker tham chiếu | `f7c6b7e:backend/app/rag/worker.py` triển khai claim ngắn, `FOR UPDATE SKIP LOCKED`, lease fencing bằng `locked_at`, reclaim, retry/backoff, permanent failure và atomic finalize. |
| Test PostgreSQL | `f7c6b7e:backend/tests/test_rag_index_postgres.py` kiểm tra `SKIP LOCKED`, fence worker cũ sau reclaim, `vector(768)`, HNSW/GIN và vector normalize. Handoff của commit ghi 5 PostgreSQL tests pass. |
| Kiểm chứng độc lập hiện tại | `git diff --check 086e7fa..f7c6b7e` pass; `docker compose --env-file .env.example config --quiet` pass; Docker targeted suite `pytest -W error -q tests/test_config.py tests/test_database_foundation.py tests/test_knowledge_models.py tests/test_rag_index_worker.py` trả `26 passed in 2.58s`. |

## Định danh và idempotency

- `rag_index_jobs.id` (UUID) là định danh một delivery/job và là khóa dùng để finalize đúng hàng đã claim.
- Aggregate là `(source_type, source_id)`, trong đó `source_type` chỉ nhận `product | knowledge`.
- Logical event là `(source_type, source_id, source_version)`. Unique constraint trên ba cột này ngăn producer tạo delivery lặp cho cùng version.
- `source_version` là số nguyên dương tăng đơn điệu khi semantic content hoặc active state thay đổi. Producer, không phải worker, sở hữu version.
- `event_type` chỉ nhận `upsert | delete`; `payload_version=1`. Version payload không hỗ trợ là lỗi permanent.
- Duplicate sau khi job đã `succeeded` không được claim lại. Nếu xử lý lặp do at-least-once delivery, version comparison, unique chunk key và atomic replacement làm side effect idempotent.
- Event cũ có `source_version` nhỏ hơn projection hiện tại được kết thúc `succeeded` như superseded; tuyệt đối không ghi đè hoặc xóa dữ liệu version mới.

## Vòng đời trạng thái

```text
pending --claim--> processing --success/superseded--> succeeded
   ^                    |
   |                    +--retryable, còn attempt--> pending (available_at tương lai)
   |                    +--permanent/hết attempt----> failed
   +--reclaim lease hết-+
```

- `succeeded` và `failed` là terminal; không được scheduler tự claim lại.
- Reindex chủ động phải tạo version/job mới theo contract producer, không hồi sinh âm thầm một job terminal.
- `rag_documents.index_status` dùng `pending | indexed | failed`: producer đặt `pending`; finalize thành công đặt `indexed`; permanent/exhausted failure đặt `failed` chỉ khi projection vẫn đúng cùng `source_version`.

## Điều kiện claim và lease

Một job đủ điều kiện claim khi:

```text
status = 'pending'
AND available_at <= now_utc
AND attempt_count < max_attempts
```

Thứ tự chọn ổn định là `(created_at, id)`. Trong transaction ngắn:

1. Khóa một hàng đủ điều kiện bằng `SELECT ... FOR UPDATE SKIP LOCKED`.
2. Đặt `status='processing'`, `locked_at=now_utc`, tăng `attempt_count` đúng một lần và xóa `last_error`.
3. Flush/commit transaction trước khi gọi embedding provider.

`locked_at` vừa là thời điểm bắt đầu lease vừa là fencing token. `ClaimedJob` giữ cặp `(id, locked_at)`. Mọi finalize phải khóa lại hàng và chỉ tiếp tục khi:

```text
id = claimed_id
AND status = 'processing'
AND locked_at = claimed_locked_at
```

Nhờ fence này, worker cũ quay lại sau khi lease đã bị reclaim không thể commit side effect hoặc trạng thái của lần claim mới. Không cần thêm `worker_id`, `lease_expires_at` hoặc token column trong schema hiện tại.

Default đã được kiểm chứng:

- `lock_timeout_seconds = 300`;
- `max_attempts = 5`;
- `retry_base_seconds = 5`;
- `retry_max_seconds = 300`.

Các giá trị phải lấy từ environment/config, không hard-code ở runner. Lease timeout phải lớn hơn timeout/batch worst-case của provider. Nếu sau này có heartbeat gia hạn lease, cần một thiết kế/migration riêng; không tự mở rộng contract trong task này.

## Transaction boundary và reclaim

Không giữ database transaction trong khi gọi provider ngoài hệ thống.

1. **Recovery + claim transaction:** đánh dấu job `pending` hoặc `processing` đã đạt `max_attempts` thành `failed`; chuyển `processing` có `locked_at < now - lock_timeout` và còn attempt về `pending`, xóa lock, đặt `available_at=now`; sau đó claim một job bằng `SKIP LOCKED`.
2. **Provider phase:** đọc projection, đối chiếu version/active state, chunk và gọi provider ngoài transaction dài.
3. **Finalize transaction:** kiểm tra ownership bằng `(id, status, locked_at)`, khóa projection; thực hiện replacement/delete chunks và cập nhật document/job trong cùng transaction.

Process chết sau claim không làm mất job: lease hết hạn cho phép reclaim. Process chết trong finalize làm transaction rollback. Process cũ hoàn tất sau reclaim bị fence loại bỏ.

Reclaim không tăng attempt trực tiếp; lần claim kế tiếp mới tăng. Vì attempt đã tăng ở claim trước, mỗi lần process thực sự nhận job vẫn được tính đúng một attempt.

## Retry, backoff và giới hạn attempt

- Backoff sau attempt thứ `n`:

```text
delay_seconds = min(retry_base_seconds * 2 ** (n - 1), retry_max_seconds)
```

- Lỗi retryable: timeout/network tạm thời, provider 429, provider 5xx, dependency tạm unavailable, hoặc projection chưa bắt kịp event version. Kết quả: `pending`, `available_at=now+delay`, `locked_at=NULL`, giữ mã lỗi đã sanitize.
- Lỗi permanent: payload version không hỗ trợ, event/type không hợp lệ, nội dung embedding rỗng, số vector/dimension sai, vector NaN/Inf/zero, projection upsert không tồn tại hoặc inactive, dữ liệu không thể sửa bằng retry. Kết quả: `failed`, xóa lease, projection cùng version thành `failed`.
- Khi `attempt_count >= max_attempts`, cả pending lẫn stale processing phải thành `failed` với `last_error='attempts_exhausted'`; không claim/reclaim tiếp.
- Lỗi hạ tầng bất ngờ ngoài taxonomy không được ghi raw exception có thể chứa secret. Runner log mã ổn định và để lease hết hạn để recovery xử lý.
- `last_error` chỉ lưu public code khớp `[a-z][a-z0-9_]{0,63}`; chuỗi không hợp lệ được thay bằng fallback code. Không lưu token, API key, cookie, raw provider response hoặc stack trace.

## Side effect và version rules

- `upsert` đúng current version: tạo chunks/vector, sau đó trong finalize transaction xóa chunks cũ và thêm tập chunks mới; đặt document `indexed`, job `succeeded`.
- `delete` đúng current version: không gọi provider; xóa chunks, đặt projection inactive/indexed và job `succeeded`.
- Projection mới hơn job: job cũ `succeeded`/superseded, không thay dữ liệu mới.
- Projection cũ hơn job: retryable `projection_version_behind`, vì producer transaction/replica có thể chưa quan sát được projection mới.
- Missing projection cho `delete` là success idempotent; missing projection cho `upsert` là permanent.
- Dynamic product facts như giá, sale, màu, size và stock không được ghi thành nguồn sự thật trong vector; retrieval downstream phải hydrate lại từ SQL.

## Kết luận migration

### Claim/retry schema

**Không cần migration bổ sung cho claim/retry.** Migration `0004_rag_content` đã có đủ:

- `id`, aggregate/version và unique idempotency;
- `status`, `attempt_count`, `available_at`, `locked_at`, `last_error`;
- claim/recovery indexes;
- timestamps phục vụ ordering/audit.

Thiết kế dùng `locked_at` làm fencing token nên không được thêm lease columns chỉ để đổi tên hoặc nhân đôi semantics.

### Side effect indexing

**Cần migration `rag_chunks` đã được contract cho phép** để worker có nơi lưu side effect. Migration tham chiếu `0005_rag_chunks` tại `f7c6b7e` bổ sung:

- FK `rag_document_id -> rag_documents.id ON DELETE CASCADE`;
- unique `(rag_document_id, source_version, chunk_index)`;
- `embedding vector(768)`, `embedding_model`, metadata JSONB và active/version fields;
- HNSW cosine, FTS GIN và document/active index.

Đây không phải thay đổi claim schema hoặc public contract. Khi tích hợp, phải serialize/renumber `0004_rag_content` và `0005_rag_chunks` với migration sibling để `alembic heads` trả đúng một head. Runtime phải fail-fast nếu `EMBEDDING_DIMENSION != 768`; đổi dimension cần migration và full reindex mới.

## Gate cho task triển khai

Task triển khai được phép tiếp tục khi branch đích chứng minh đủ các điều kiện sau:

1. Có dependency commits hoặc equivalent changes của BE-03-GAP, BE-04-GAP, BE-15 producer/schema.
2. Có đúng một Alembic head và `rag_index_jobs` khớp model/migration.
3. Migration chunk dùng `vector(768)` và PostgreSQL có extension `vector`.
4. Không đổi endpoint, response schema hoặc event allow-list.
5. Unit tests cover claim, retry/backoff, exhausted/permanent, stale reclaim, duplicate/superseded và secret-safe error.
6. PostgreSQL tests cover concurrent `SKIP LOCKED`, expired-lease fencing và vector/index migration.

Nếu thiếu bất kỳ điều kiện nào trên branch thực thi, task triển khai phải chuyển **BLOCKED** với commit/tree và lệnh tái hiện cụ thể thay vì tạo schema hoặc contract thay thế.

## Rủi ro còn lại

- Các dependency/implementation hiện nằm trên task branches, chưa nằm trong `main`; merge order và Alembic serialization vẫn là trách nhiệm tích hợp.
- Delivery là at-least-once; tính đúng đắn đến từ idempotent projection và fencing, không phải cam kết exactly-once transport.
- Provider tại commit tham chiếu là deterministic stub; adapter Gemini và end-to-end retrieval/freshness thuộc các task RAG tiếp theo.
- Unit/worker tests chưa đủ để tuyên bố RAG-11/RAG-12 end-to-end PASS; vẫn cần retrieval và live SQL hydration tests trên PostgreSQL/pgvector thật.
