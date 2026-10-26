# Task breakdown và dependency

> **Kế hoạch thực thi hiện hành:** Kanban phải theo critical path `MVP-01..07` trong [`mvp-product-rag-scope.md`](mvp-product-rag-scope.md). Các task BE/FE/RAG/QA đầy đủ bên dưới là backlog lịch sử; task ngoài catalog công khai, product detail tối giản và chat RAG sản phẩm phải archive khỏi board MVP.

## 1. Mục tiêu điều phối

Chia việc cho bốn profile để triển khai theo contract, giảm xung đột và không bắt frontend/RAG đoán API. Tài liệu này là kế hoạch thực hiện; ở bước khởi tạo hiện tại **chưa triển khai source code sản phẩm**.

## 2. Nguyên tắc dependency

- `D0` là các tài liệu hiện có: `request.md`, `AGENTS.md`, `docs/*`.
- Backend phải cung cấp migration/OpenAPI/fixture trước khi consumer tích hợp thật.
- Frontend có thể dựng skeleton/mocks theo contract sau khi contract freeze, nhưng không đánh dấu tích hợp hoàn tất trước API.
- RAG phụ thuộc schema product/content/chat và API chat/admin; retrieval SQL có thể làm sau khi seed/catalog ổn định.
- QA tham gia từ đầu để viết test/fixture, nhưng E2E chỉ bắt đầu khi các vertical slice ready.
- Mỗi task chỉ done khi có test và handoff theo `AGENTS.md`.

## 3. Thứ tự tổng thể

```text
P0 Documentation/contract freeze (đã khởi tạo)
  ↓
P1 Repo + Docker + DB foundation
  ↓
P2 Auth + catalog + seed + public UI
  ↓
P3 Cart + pricing + checkout + orders
  ↓
P4 Admin CRUD + content + indexing foundation
  ↓
P5 Hybrid RAG + chat widget + support handoff
  ↓
P6 Cross-profile integration + full acceptance + hardening
```

Các task cùng phase chỉ chạy song song khi dependency trực tiếp đã đáp ứng.

## 4. `shop-backend`

| ID | Task/deliverable | Depends on | Consumer/handoff |
|---|---|---|---|
| BE-01 | Khởi tạo FastAPI structure, config, error envelope, health, test harness | D0 | FE/RAG/QA |
| BE-02 | Docker Compose cho API/DB pgvector/web placeholder/worker và `.env.example` | BE-01 | Tất cả |
| BE-03 | Migration foundation, conventions và CI/local commands | BE-02 | RAG/QA |
| BE-04 | Identity schema, auth session, customer/admin RBAC, forgot/reset demo | BE-03 | FE-02, QA |
| BE-05 | Catalog schema/API: categories/products/images/colors/sizes/variants/labels | BE-03 | FE-03, RAG-03 |
| BE-06 | Seed deterministic đúng 100 products + variants/content/users và verifier | BE-04, BE-05, BE-15 schema content | FE/RAG/QA |
| BE-07 | Search/filter/sort/facets/related, pagination và SQL indexes | BE-05 | FE-03, RAG-04 |
| BE-08 | Cart guest/customer + ownership/version + stock validation | BE-04, BE-05 | FE-04 |
| BE-09 | Pricing/shipping/coupon rules và API | BE-08 | FE-04, QA |
| BE-10 | Checkout transaction, stock lock/movements, COD + online demo, idempotency | BE-09 | FE-05, QA |
| BE-11 | Order history/detail/cancel và state machine | BE-10 | FE-02, FE-05 |
| BE-12 | Admin dashboard, product/variant/media/customer/order CRUD APIs | BE-04, BE-05, BE-10 | FE-06 |
| BE-13 | Coupon admin API | BE-09, BE-12 auth | FE-06 |
| BE-14 | Local media upload/serve với validation | BE-05 | FE-03, FE-06 |
| BE-15 | Knowledge/content schema + admin CRUD + index status/outbox job | BE-03, BE-04 | RAG-01, FE-06 |
| BE-16 | Chat session/message/source + support ticket schema/API shell | BE-04, BE-15 | RAG-02, FE-07 |
| BE-17 | OpenAPI stabilization, contract fixtures, README run/migrate/seed/demo login | Tất cả BE trước | FE/RAG/QA |

Lưu ý thứ tự seed: BE-06 có thể chia `catalog seed` sau BE-05 và `knowledge seed` sau BE-15; bản seed hoàn chỉnh chỉ done khi cả hai phần và verifier pass.

## 5. `shop-frontend`

| ID | Task/deliverable | Depends on | Consumer/handoff |
|---|---|---|---|
| FE-01 | Vue 3/Vite structure, router, API client, design tokens, responsive shell | D0, contract freeze | QA |
| FE-02 | Auth/account routes, guards, register/login/reset, order history shell | FE-01, BE-04 contract | QA |
| FE-03 | Home/category/search/filter/sort/product detail/related + variant selector | FE-01, BE-05, BE-07, BE-14 URLs | QA, RAG cards |
| FE-04 | Cart CRUD, coupon, stock/price conflict UX, shipping quote | FE-03, BE-08, BE-09 | FE-05, QA |
| FE-05 | 6-step checkout, COD/online-demo notice, success/guest lookup, cancel/history | FE-02, FE-04, BE-10, BE-11 | QA |
| FE-06 | Admin layout/dashboard và CRUD product/variant/order/customer/coupon/content/ticket | FE-01, BE-12, BE-13, BE-15, BE-16 | QA |
| FE-07 | Chat widget shell, session persistence, messages, product cards, handoff button | FE-01, BE-16, RAG-06 | QA |
| FE-08 | Accessibility/responsive/error/loading/empty states và link audit | FE-02..07 | QA |
| FE-09 | Frontend tests, production build check và README frontend section | FE-01..08 | QA |

Frontend có thể dùng contract fixtures sau FE-01, nhưng trước khi done phải test với backend thật; Gemini key tuyệt đối không nằm trong bundle.

## 6. `shop-rag`

| ID | Task/deliverable | Depends on | Consumer/handoff |
|---|---|---|---|
| RAG-01 | Chunking/normalization/embedding interfaces, config model/dimension, unit tests | D0, BE-15 schema | QA |
| RAG-02 | Index job worker idempotent, version swap, retry/failure status | RAG-01, BE-15 | Admin/QA |
| RAG-03 | Product semantic document projection, update/delete reindex hooks | RAG-02, BE-05 | RAG-04 |
| RAG-04 | Structured SQL retrieval theo category/budget/color/size + hydration live | BE-07, BE-06, RAG-03 | RAG-06 |
| RAG-05 | Knowledge vector + keyword retrieval, thresholds/ranking/citations | RAG-02, BE-06 content | RAG-06 |
| RAG-06 | Intent/filter extraction, hybrid orchestration, Gemini structured output | RAG-04, RAG-05, BE-16 | FE-07, QA |
| RAG-07 | Guardrails: scope, insufficient data, injection, ID/price/stock validator | RAG-06 | QA |
| RAG-08 | Conversation state/context window và anonymous session isolation | RAG-06, BE-16 | FE-07, QA |
| RAG-09 | Support handoff integration và transcript linkage | RAG-08, BE-16 | FE-06/07, QA |
| RAG-10 | Eval corpus tiếng Việt, provider stub + Gemini smoke, observability/fallback | RAG-02..09 | QA |
| RAG-11 | README/config/index/reindex operational guide | RAG-01..10, BE-17 | Tất cả |

RAG không được coi embedding là source of truth cho field động. BE chịu ownership transaction/schema; RAG cung cấp service/repository logic qua boundary thống nhất, không fork schema riêng.

## 7. `shop-qa`

| ID | Task/deliverable | Depends on | Consumer/handoff |
|---|---|---|---|
| QA-01 | Traceability matrix từ `acceptance-test.md`, risk và test data plan | D0 | Tất cả |
| QA-02 | Test harness: API integration, DB reset/seed verifier, browser E2E | BE-01/02 contracts, FE-01 | Tất cả |
| QA-03 | Bootstrap/migration/seed/security-secret tests | BE-02, BE-03, BE-06 | Backend |
| QA-04 | Auth/RBAC/ownership API và UI tests | BE-04, FE-02 | BE/FE |
| QA-05 | Catalog/search/filter/sort/variant/responsive tests | BE-05..07, FE-03 | BE/FE |
| QA-06 | Cart/coupon/concurrent stock/checkout/order/cancel E2E | BE-08..11, FE-04/05 | BE/FE |
| QA-07 | Admin CRUD/dashboard/media/privacy/state tests | BE-12..15, FE-06 | BE/FE |
| QA-08 | RAG retrieval/grounding/live price-stock/reindex/injection/provider failure eval | RAG-02..10 | RAG/BE |
| QA-09 | Chat widget/session/product cards/ticket transcript E2E | FE-07, RAG-08/09, BE-16 | FE/RAG/BE |
| QA-10 | Link crawl, browser console, viewport matrix, a11y smoke | FE-08 | FE |
| QA-11 | Clean-room full acceptance, defect retest và release report | BE-17, FE-09, RAG-11, QA-03..10 | Điều phối |

QA viết test case/fixture sớm theo contract, không chờ toàn bộ code; bug phải ghi actual/expected, repro, evidence, severity và owner.

## 8. Critical path và task chạy song song

### Critical path

```text
D0
→ BE-01 → BE-02 → BE-03
→ BE-05 → BE-07 → BE-08 → BE-09 → BE-10 → BE-11
→ BE-15 → RAG-01 → RAG-02 → RAG-04/05 → RAG-06 → RAG-07/08/09
→ FE-07
→ QA-08/09
→ QA-11
```

BE-04 phải hoàn tất trước các luồng account/admin; BE-06 phải hoàn tất trước các bài test dữ liệu/RAG đầy đủ.

### Song song an toàn

- Sau D0: BE-01, FE-01 và QA-01 có thể chạy song song.
- Sau BE-03: BE-04, BE-05 và BE-15 schema có thể chia module song song nếu migration ownership được điều phối.
- Sau BE-05 contract: FE-03, BE-07 và RAG-03 chuẩn bị projection có thể song song.
- Sau BE-10: FE-05, BE-12 và QA-06 có thể bắt đầu theo slice đã ready.
- Sau BE-15: RAG-01/02 và FE-06 phần content có thể song song.
- RAG-04 và RAG-05 chạy song song rồi hội tụ ở RAG-06.
- QA automation theo từng slice chạy song song với implementation sau khi interface ổn định.

## 9. Milestone và gate

### M0 — Contract ready

- Các docs hiện tại reviewed; câu hỏi mở được chốt.
- Không có source code sản phẩm được yêu cầu ở milestone khởi tạo này.

### M1 — Foundation ready

- Compose/health/migration/config/test harness hoạt động trên DB mới.
- Gate: QA-02/03 bootstrap phần tương ứng pass.

### M2 — Commerce core ready

- Auth, catalog đúng 100 seed, storefront, cart, COD checkout, order/admin status.
- Gate: CAT/ADM P0 không phụ thuộc RAG pass.

### M3 — RAG ready

- Content/product index, hybrid retrieval, live hydration, widget, support ticket.
- Gate: RAG P0 pass với provider stub và Gemini smoke khi có key.

### M4 — Acceptance ready

- Admin đầy đủ, responsive/link/console, README clean start.
- Gate: QA-11 tất cả P0 pass, không secret, deviation được ghi rõ.

## 10. Handoff bắt buộc

Mỗi profile bàn giao:

- Task ID và acceptance IDs liên quan.
- Files/schema/API/config đã thay đổi.
- Migration/seed impact và rollback/reset.
- Commands test đã chạy + kết quả thực tế.
- OpenAPI/fixture/screenshot/log cần cho consumer.
- Known limitations/risk; không gọi limitation nằm trong P0 là “ngoài phạm vi” nếu `request.md` yêu cầu.

## 11. Điểm cần chốt trước implementation

Các default dưới đây đã được kiến trúc đề xuất nhưng điều phối nên khóa trước khi code:

1. JWT cookie/CSRF policy và cơ chế demo password reset.
2. `EMBEDDING_DIMENSION` theo embedding model được chọn trước migration vector.
3. Định nghĩa doanh thu demo và best-selling (đơn hoàn thành hay mọi đơn không hủy).
4. Giá trị shipping fee/free threshold trong `.env.example`.
5. Guest order lookup/token và retention chat demo.
6. Giới hạn upload, pagination, rate limit và RAG top-k/threshold ban đầu.

Nếu chưa chốt, dùng giá trị cấu hình/an toàn và ghi rõ trong README/test; không hard-code rải rác.
