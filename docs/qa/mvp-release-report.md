# Báo cáo release MVP catalog và chat RAG

Ngày kiểm thử: 2026-10-26

Task: `t_077bc29c`

Baseline tích hợp đã review: `60667715d5b18806e92022b7313ef86637df3a7c` trên `ab09646e67302726c8ba004029f049b67abac837`.

## Phạm vi và kết luận

Release gate chỉ gồm catalog công khai, trang chi tiết tối giản và chat RAG sản phẩm theo `docs/mvp-product-rag-scope.md`. Auth, cart, checkout, order, admin và support không quyết định kết quả.

**Kết luận: PASS với provider stub deterministic.** Không có lỗi P0 còn mở trong phạm vi MVP. Live Gemini chưa chạy vì môi trường kiểm thử không có credential thật; không có tuyên bố Gemini smoke pass.

## Môi trường clean-room

- Docker Engine 28.1.1, Docker Compose v2.35.1.
- Compose project cô lập: `shop-mvp07`.
- Host port kiểm thử: frontend `35176`, API `38000`, PostgreSQL `35432` để tránh xung đột với stack khác trên máy.
- Database clean `shop_clean` được migrate từ rỗng tới Alembic head `0005_rag_chunks`.
- Seed/verifier: 4 category, 20 product, 60 variant; reseed cho snapshot giống hệt.
- Reindex: 20 projection được tạo; worker xử lý `succeeded=20`.
- Sau khi sửa thứ tự README thành migrate trước rồi mới start toàn stack, API, DB, frontend và worker đều healthy; log mới của API/frontend/worker không có ERROR.

Lượt thử đầu tiên làm đúng README cũ đã khởi động worker trước migration và tạo `rag_worker_iteration_failed`. README gốc và backend đã được sửa sang thứ tự fail-safe: start DB → migrate → seed/verify/reindex → start stack.

## Kết quả acceptance gate

| Gate | Kết quả | Bằng chứng |
|---|---|---|
| MVP-BOOT-01 | PASS | Compose config/build, migration `0001..0005`, seed, verify, reindex và start sạch thành công. |
| MVP-CAT-01 | PASS | API/UI trả 20 sản phẩm seed; trang đầu 12 card; pagination, empty/error được unit/integration coverage. |
| MVP-CAT-02 | PASS | 16 PostgreSQL catalog integration test pass; E2E kiểm search và filter category/price/color/size. |
| MVP-CAT-03 | PASS | E2E mở slug canonical, hiển thị giá/stock/variant và ảnh API-hosted; link chat mở detail hợp lệ. |
| MVP-RAG-01 | PASS | 10 PostgreSQL retrieval cases trong suite 17 test và E2E hard-filter pass. |
| MVP-RAG-02 | PASS | E2E assert source product IDs đúng bằng product card IDs, chunk IDs không rỗng và URL allow-list. |
| MVP-RAG-03 | PASS | PostgreSQL test `test_price_and_stock_are_hydrated_live_without_reindex` pass. |
| MVP-RAG-04 | PASS | Missing combination, ngoài phạm vi, prompt injection, assistant-history injection và hallucinated ID đều fail-closed. |
| MVP-RAG-05 | PASS có deviation | Stub deterministic pass; provider failure được sanitize. Live Gemini không chạy vì không có credential. |
| MVP-UI-01 | PASS | Playwright Chromium tại 390×844 và 1366×768; listing/detail/chat pass, không horizontal overflow, dialog nằm trong viewport. |
| MVP-TECH-01 | PASS | Backend/frontend/QA suites, build, console/request/link smoke, Compose config và secret scan pass. |

## Lệnh và kết quả thực tế

### Bootstrap và PostgreSQL

- `docker compose --env-file .env.example --project-name shop-mvp07 config --quiet` — PASS.
- `docker compose ... run --rm api alembic upgrade head` trên database rỗng — PASS, head `0005_rag_chunks`.
- `python -m app.cli.seed_catalog` — PASS: 4/20/60.
- `python -m app.cli.verify_catalog` — PASS, idempotent snapshot.
- `python -m app.cli.reindex_products` — PASS: `created=20 updated=0 deactivated=0`.
- `docker compose ... up --build -d --force-recreate api rag-worker frontend` — PASS; 4 service healthy.
- Queue sau worker: `succeeded|20`.

### Backend

- Full image suite: **144 passed, 33 skipped**; các skip là integration suite cần PostgreSQL URL riêng.
- Fresh PostgreSQL migration/projection/index/retrieval suite: **17 passed**.
- Fresh PostgreSQL catalog API suite: **16 passed**.
- Guardrail/provider/final revalidation focused suite: **6 passed**.

### Frontend và browser

- `VITE_API_BASE_URL=http://127.0.0.1:38000/api/v1 npm test` — **90 passed**.
- `VITE_API_BASE_URL=http://127.0.0.1:38000/api/v1 npm run build` — PASS, 79 modules transformed.
- QA TypeScript `tsc --noEmit` — PASS.
- Legacy shell/link/console smoke sau khi bỏ hai route đã thành feature thật khỏi danh sách placeholder — **50 passed**.
- MVP Playwright trên desktop/mobile — **6 passed**; gồm catalog/search/detail, chat/product cards/link, SQL filters, grounding, missing data, out-of-scope, injection, runtime console/request và responsive bounds.

### Bảo mật cơ bản

- `npm ci` cho frontend và QA: 0 vulnerability được npm audit báo cáo.
- Pattern scan trên 169 file tracked: không thấy Google/OpenAI/GitHub credential hoặc private key thật.
- Các URL PostgreSQL trong source chỉ là placeholder/test (`change-me`, `shop`, giá trị redacted); không có `.env` runtime được track.

## Deviation và rủi ro còn lại

1. **Không chạy Gemini thật**: không có `GEMINI_API_KEY` hợp lệ; chỉ stub, structured-provider unit test và provider-failure fallback được xác minh.
2. **Browser engine**: browser acceptance chạy Google Chrome/Chromium; chưa chạy Firefox/WebKit.
3. **Hạ tầng máy dùng chung**: Docker address pool và port mặc định đã bị các stack khác chiếm. QA dùng project/port cô lập; đây không phải lỗi ứng dụng.
4. Các route placeholder ngoài MVP vẫn được smoke về shell/link/console nhưng không được tính là feature acceptance.
