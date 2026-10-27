# QA-01 — Risk-based test plan

## 1. Mục tiêu và phạm vi

Kế hoạch này ưu tiên kiểm thử theo rủi ro cho website demo Mộc Store. Phạm vi bao gồm bootstrap/Compose, FastAPI/PostgreSQL, storefront, auth, cart/pricing/checkout/order, admin, RAG/chat/support, responsive và bảo mật cơ bản. Không kiểm thử production HA/CDN/payment/shipping/email/live-chat thật ngoài việc xác nhận chúng không bị tích hợp ngoài phạm vi.

Tại QA-02 hiện chỉ FE-01 và BE-01..03 tồn tại. Automation runnable chỉ bao phủ backend foundation, frontend unit/application shell, route placeholder và Compose syntax. Các luồng nghiệp vụ còn lại là planned, không được báo PASS.

## 2. Chiến lược ưu tiên

- Impact: 3 = sai tiền/stock/quyền/secret hoặc hệ thống không chạy; 2 = chặn luồng chính/sai nội dung quan trọng; 1 = ảnh hưởng nhỏ/thẩm mỹ.
- Likelihood: 3 = logic phức tạp/thay đổi nhiều/tích hợp ngoài; 2 = thường gặp; 1 = đơn giản/ổn định.
- Risk score = Impact × Likelihood.
- P0: score 6–9 hoặc yêu cầu bảo mật/transaction bắt buộc; chạy mỗi release candidate.
- P1: score 3–4; chạy sau P0 và trước release nếu dependency sẵn sàng.
- P2: score 1–2; regression mở rộng/manual exploratory.

## 3. Risk register

| Risk ID | Rủi ro | I×L | Priority | Kiểm soát/test chính |
|---|---|---:|---|---|
| RK-01 | Hệ thống không bootstrap được từ DB mới/Compose/migration | 3×3=9 | P0 | Clean-room, health, migration up, README replay |
| RK-02 | Seed không đúng 100 hoặc không deterministic | 3×3=9 | P0 | Count DB+API, reset/reseed snapshot, uniqueness/orphan checks |
| RK-03 | Sai giá/coupon/shipping/total do float hoặc trust client | 3×3=9 | P0 | Unit boundary/table tests, API tamper, DB order snapshot oracle |
| RK-04 | Oversell hoặc stock bị trừ/hoàn nhiều lần khi concurrent/retry | 3×3=9 | P0 | Concurrent integration, lock/idempotency/inventory movement assertions |
| RK-05 | Lộ/chỉnh tài nguyên user khác hoặc admin API thiếu RBAC | 3×3=9 | P0 | Role/ownership matrix, ID substitution, cookie/session isolation |
| RK-06 | Secret/password/token xuất hiện repo, bundle, log hoặc response | 3×2=6 | P0 | Tracked-file/bundle/log/schema scan; negative API assertions |
| RK-07 | RAG bịa price/stock/policy/product/link | 3×3=9 | P0 | Provider stub adversarial output, validator test, SQL/source oracle |
| RK-08 | RAG dùng vector stale thay vì SQL live | 3×3=9 | P0 | Mutate price/stock, query before reindex, verify hydrated fields |
| RK-09 | Prompt injection/user/source làm lộ dữ liệu/rule | 3×2=6 | P0 | Injection corpus, allow-list/tool isolation, output scan |
| RK-10 | Anonymous chat/session transcript bị đọc bằng UUID | 3×2=6 | P0 | Token ownership/cross-session API tests |
| RK-11 | Checkout retry tạo nhiều order/ticket/coupon redemption | 3×2=6 | P0 | Same/different idempotency key and transaction assertions |
| RK-12 | Admin update content/product không reindex đúng version | 2×3=6 | P0 | Job idempotency, atomic version swap, inactive source test |
| RK-13 | Search/filter/sort trả item vi phạm hard filter | 2×3=6 | P0 | Deterministic catalog oracle, pairwise combinations/boundaries |
| RK-14 | Order transition/cancel rule sai, stock restore sai | 3×2=6 | P0 | State transition table + audit movement |
| RK-15 | UI dead link/HTTP/JS runtime error ở flow chính | 2×3=6 | P0 | Route/link crawl, response/request/console listeners |
| RK-16 | Layout/widget che CTA hoặc overflow mobile | 2×2=4 | P1 | 5 viewport matrix, bounding-box/visual/manual checks |
| RK-17 | Gemini timeout làm hỏng commerce API | 3×1=3 | P1 | Dependency fault injection/circuit fallback/isolation |
| RK-18 | Upload giả MIME/path traversal/file quá lớn | 3×2=6 | P0 | Malicious fixture corpus và filesystem boundary |
| RK-19 | Forgot password/email response lộ account tồn tại | 2×2=4 | P1 | Equal status/body/timing tolerance; token expiry/use-once |
| RK-20 | Flaky tests do shared DB/session/provider | 2×2=4 | P1 | Per-run namespace, deterministic seed, stub provider, cleanup/trace |

### 3.1. Risk register cho vertical slice `return_policy`

Các risk dưới đây là P0 của gate RET hiện hành và được trace hai chiều với
`RET-RAG-01..06` trong `docs/qa/return-policy-rag-test-plan.md`. Corpus thực thi dùng
`qa/fixtures/return-policy-questions.json`.

| Risk ID | Acceptance | Rủi ro | I×L | Kiểm soát/test chính |
|---|---|---|---:|---|
| RET-RK-01 | RET-RAG-01 | Intent policy chiếm nhầm product/out-of-scope hoặc bỏ sót diễn đạt lại/follow-up | 3×3=9 | Corpus direct/paraphrase/follow-up/mixed và product regression; allow-list intent; follow-up chỉ route policy khi history policy rõ |
| RET-RK-02 | RET-RAG-02 | Seed thiếu/sai/trùng canonical source hoặc job/version không idempotent | 3×3=9 | Clean DB migrate→seed→verify→index, reseed snapshot/count, cố ý mutate/remove fixture để verifier fail closed |
| RET-RK-03 | RET-RAG-03 | Retrieve FAQ, sai locale, inactive, pending/failed hoặc stale chunk; rank/dedupe không ổn định | 3×3=9 | PostgreSQL setup cô lập cho từng state; assert active/indexed/current/vi/type; keyword+semantic; source/chunk membership và dedupe |
| RET-RK-04 | RET-RAG-04 | Model đảo 07 ngày đổi/03 ngày trả, bịa điều kiện/phí, tuyệt đối hóa hàng sale hoặc tạo citation giả | 3×3=9 | Canonical fact allow-list + forbidden claims; case riêng deadline/phí hai chiều/sale; `products=[]`; output/citation ngoài retrieval set → `insufficient_data` |
| RET-RK-05 | RET-RAG-05 | Trộn version cũ, dùng source archived/rỗng hoặc làm theo user/source injection và fact xung đột | 3×3=9 | Before/after reindex/archive; stale-only/current+stale; user/source injection; conflicting source fail closed; scan prompt/secret |
| RET-RK-06 | RET-RAG-06 | API/widget làm mất contract product, hiển thị card/link policy giả hoặc biến Zalo text thành integration/live chat | 3×2=6 | API schema additive + product regression; E2E 1366×768/390×844; citation title-only; không card/UUID URL/action; console/request listeners |

## 4. Test levels và ownership

| Loại | Mục tiêu | Ví dụ | Khi chạy |
|---|---|---|---|
| Unit | Rule thuần, nhanh, mọi branch/boundary | pricing, coupon, shipping, state machine, RAG validator | Mỗi thay đổi/PR |
| Integration | DB/migration/transaction/repository/job | checkout lock, seed, reindex, persistence | Mỗi vertical slice; nightly/full |
| API | Contract/status/error/RBAC/ownership/idempotency | `/api/v1` public/account/admin/chat | Mỗi vertical slice và regression |
| E2E | Journey user thật qua browser | guest COD, history, admin CRUD, handoff | Smoke mỗi build; full trước release |
| Responsive | Layout/touch/overflow/overlap | 360×800, 390×844, 768×1024, 1366×768, 1440×900 | UI slice và release |
| RAG evaluation | Retrieval, grounding, freshness, safety | SQL hard filters, citations, injection, failure | Provider stub mỗi build; Gemini smoke có key |

Không dồn mọi oracle vào E2E. Rule tiền/stock/state cần unit+integration; E2E chỉ xác nhận wiring và UX. Provider thật chỉ là smoke không deterministic, không thay thế provider stub.

## 5. Phạm vi theo phase/dependency

1. Foundation (hiện tại): backend 7 test, frontend 31 test, build, Compose config, Playwright shell/routes 2 viewport.
2. BE-04/FE-02: auth/RBAC/ownership/reset.
3. BE-05..07/FE-03/BE-06: catalog và seed đúng 100; search/filter/sort/variant.
4. BE-08..11/FE-04..05: pricing/cart/concurrency/checkout/order; ưu tiên P0 transaction.
5. BE-12..16/FE-06: admin/media/privacy/content/ticket.
6. RAG-01..10/FE-07: deterministic retrieval/guardrail/session/handoff; Gemini smoke nếu có key.
7. FE-08/09 và BE-17: full viewport/link/console/clean-room acceptance.

## 6. Kỹ thuật thiết kế test

- Boundary: quantity 0/1/stock/stock+1; shipping threshold −1/exact/+1; coupon start/end; price 0/large VND.
- Decision table: coupon validity; order transitions; role × endpoint × ownership; variant active/stock.
- Pairwise: category × price × size × color; viewport × route × widget state.
- State transition: order, ticket, index job, cart.
- Concurrency/idempotency: last stock, same checkout key, cancel retry, support ticket retry, index retry.
- Metamorphic/oracle: changing SQL price/stock must change RAG/API result without relying on vector refresh.
- Adversarial: SQL/XSS/control chars/path traversal/prompt injection/hallucinated IDs.

## 7. Environment và evidence

- Local Docker Compose từ `.env.example`; secret test riêng, không commit.
- Database mới cho bootstrap; database test riêng cho destructive reset.
- Chrome desktop/mobile là baseline hiện tại; thêm Firefox/WebKit hoặc browser thứ hai trước QA-11 khi khả thi.
- Stub Gemini deterministic cho regression; Gemini thật chỉ khi `GEMINI_API_KEY` test được cung cấp ngoài repo.
- Mỗi run lưu: commit hash, command, tool/browser version, viewport, pass/fail/skip counts, logs/traces/screenshots khi fail, DB product count và deviations.

## 8. Entry criteria

- Contract/schema của slice đã chốt; dependency trong `task-breakdown.md` hoàn tất hoặc có fixture được điều phối chấp thuận.
- Migration/seed/reset command và demo credentials được bàn giao nếu test cần DB.
- Endpoint/UI không còn placeholder cho behavior được test.
- Test environment không dùng production data/secret; health check pass.
- Với RAG: corpus/version/provider stub và expected source IDs có sẵn.

## 9. Exit criteria

- Tất cả P0 applicable pass trên clean run, không flaky chưa xử lý; không có blocker/critical.
- P1 fail phải có defect owner, impact và quyết định rõ.
- Không có secret thật; browser console không có lỗi nghiêm trọng ở P0.
- Migration+seed chạy lại được, đúng 100 products khi BE-06 tồn tại.
- RAG P0 chứng minh grounding/source/SQL freshness, không chỉ so keyword prose.
- Báo cáo có command, counts, commit, evidence và danh sách planned/skipped kèm lý do dependency.

## 10. Triage và nguyên tắc dừng

- Dừng release/test bị ảnh hưởng ngay khi có corruption, oversell, sai total, lộ secret/PII, bypass RBAC hoặc hallucinated dynamic fact.
- Không sửa hành vi sản phẩm hoặc hạ assertion để test pass. Ghi defect gồm actual/expected, repro, evidence, severity và owner.
- Flaky test bị cách ly chỉ sau khi có defect; không retry vô hạn để che lỗi.
- Test planned vì feature chưa tồn tại không được tạo implementation giả và không được báo skip như một PASS.
