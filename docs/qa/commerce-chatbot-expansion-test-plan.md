# EXP-QA-01 — Traceability, oracle và corpus commerce chatbot

## 1. Phạm vi và nguồn sự thật

Kế hoạch này hiện thực hóa `EXP-CONTRACT-01..10` cho tám nhóm nghiệp vụ trong
[contract mở rộng](../commerce-chatbot-expansion-contract.md). Yêu cầu trực tiếp ngày
2026-11-03 ghi đè addendum MVP cũ ở phần xung đột; các quyết định catalog và
`return_policy` cũ chỉ còn hiệu lực khi không xung đột. Không sửa
[`request.md`](../../request.md).

Nguồn bắt buộc đã đối chiếu:

- [`request.md`](../../request.md) và [`AGENTS.md`](../../AGENTS.md)
- [`docs/api-contract.md`](../api-contract.md)
- [`docs/database-schema.md`](../database-schema.md)
- [`docs/rag-design.md`](../rag-design.md)
- [`docs/acceptance-test.md`](../acceptance-test.md)

Corpus máy đọc là `qa/fixtures/commerce-chatbot-expansion.json`; schema là
[`commerce-chatbot-expansion.schema.json`](../../qa/fixtures/commerce-chatbot-expansion.schema.json).
Validator `qa/scripts/validate-commerce-expansion.mjs` kiểm schema, cross-reference,
đủ tám nhóm, đủ direct/paraphrase/follow-up, các tag rủi ro bắt buộc và link tài liệu.

Tại thời điểm lập kế hoạch, commerce API/schema và intent mở rộng chưa được triển
khai. Vì vậy 44 case đều là **Planned**, không phải PASS/SKIP. Oracle được khóa
trước implementation để worker không dùng câu trả lời model làm kết quả mong đợi.

## 2. Quy ước oracle

- `read_only`: chỉ đọc dữ liệu đã authorize; không token xác nhận, không side effect.
- `proposal`: chat trả `proposed_action` sau authorization/read validation; không
  thực hiện mutation trong cùng lượt.
- `mutation`: endpoint typed nhận confirmation token khi contract yêu cầu,
  `Idempotency-Key`, reauthorize/revalidate và commit transaction.
- Oracle là HTTP status + error code + DB row/movement/version + retrieval/source
  membership + DOM/network recorder. Prose của model không bao giờ là oracle.
- Dynamic price, promotion, color, size, stock, cart/order/payment/refund status
  lấy từ PostgreSQL tại request hiện tại. Vector chỉ hỗ trợ retrieval.
- Payment/refund luôn ghi `demo`/`mô phỏng`; amount là integer VND từ SQL; số
  external payment/refund call mong đợi luôn bằng `0`.
- Với deny ownership, ưu tiên `404 RESOURCE_NOT_FOUND` để không lộ resource. Nếu
  OpenAPI cuối khóa `403`, backend và fixture phải đổi đồng bộ trước implementation,
  không cho test chấp nhận cả hai.

## 3. Traceability `EXP-CONTRACT-01..10`

| Acceptance ID | Owner chính | Layer | Fixture tiêu biểu | Expected result khóa |
|---|---|---|---|---|
| EXP-CONTRACT-01 | shop-rag | unit, API, RAG eval | EXP-POL-001, EXP-PROD-001, EXP-CART-002, EXP-ORD-001, EXP-LOOK-001, EXP-REF-001, EXP-GREET-001, EXP-SAFE-004 | Đủ tám nhóm route vào allow-list; unknown/injection fail closed, không mutation. |
| EXP-CONTRACT-02 | shop-backend | API, contract review | EXP-CART-005, EXP-ORD-006 | Method/path/header/status/error code khớp OpenAPI và consumer types. |
| EXP-CONTRACT-03 | shop-backend | integration, API | EXP-CART-004, EXP-LOOK-004, EXP-LOOK-005, EXP-REF-006 | Đổi resource ID, guest token hoặc owner không đọc/sửa resource khác. |
| EXP-CONTRACT-04 | shop-backend | unit, integration, API | EXP-ORD-003, EXP-ORD-005, EXP-ORD-006, EXP-REF-003 | Replay cùng key/payload trả snapshot; payload khác trả 409; một business mutation và một stock movement. |
| EXP-CONTRACT-05 | shop-backend | unit, integration, API | EXP-ORD-004, EXP-REF-008 | Transition sai bị từ chối; status, stock và movement không đổi. |
| EXP-CONTRACT-06 | shop-rag + shop-backend | unit, integration, API, RAG eval | EXP-CART-002/003, EXP-REF-004..008, EXP-SAFE-002/004 | Proposal tách mutation; expired/replayed/wrong-owner/changed payload/changed state fail closed. |
| EXP-CONTRACT-07 | shop-qa | integration, API, E2E | EXP-ORD-002/007, EXP-LOOK-002, EXP-REF-003 | Nhãn demo rõ, VND từ SQL, network/DNS external call count = 0, không credential provider thật. |
| EXP-CONTRACT-08 | shop-rag | integration, API, RAG eval | EXP-POL-004/005, EXP-PROD-004, EXP-SAFE-005 | Knowledge current và SQL live là nguồn thật; stale/provider failure/injection an toàn. |
| EXP-CONTRACT-09 | shop-frontend | E2E, responsive | EXP-GREET-002, EXP-ORD-002, EXP-REF-001 | Copy tiếng Việt/VND/demo; desktop/mobile không che CTA, không console/request error ngoài expected. |
| EXP-CONTRACT-10 | shop-qa | integration, E2E, review | EXP-POL-005, EXP-ORD-007, EXP-SAFE-004 | Migration/seed/run sạch; suite thật và secret scan pass; thiếu credential Gemini là SKIP riêng, không PASS. |

Mapping requirement → fixture nằm trong `traceability[].fixture_ids`; mapping
fixture → requirement nằm trong `cases[].acceptance_ids`. Danh sách traceability
chứa các case tiêu biểu, không lặp lại toàn bộ corpus. Validator buộc từng fixture
tiêu biểu map ngược về đúng acceptance ID, và từ chối ID/case không tồn tại.

## 4. Corpus tám nhóm

| Nhóm | Intent | Direct / paraphrase / follow-up | Phân lớp side effect |
|---|---|---|---|
| 01 Chính sách | `policy_question` | EXP-POL-001 / 002 / 003 | read-only; source injection và provider failure bổ sung ở 004/005 |
| 02 Sản phẩm/so sánh | `product_search`, `product_compare` | EXP-PROD-001 / 002 / 003 | read-only; SQL-live/vector-stale ở 004 |
| 03 Giỏ hàng | `cart_read/add/update/remove` | EXP-CART-001 / 002/005 / 003 | read-only, proposal, mutation tách biệt; IDOR ở 004 |
| 04 Đơn/payment demo/hủy | `order_create/cancel`, `payment_demo_status` | EXP-ORD-001/004/007 / 002/005/006/008 / 003 | proposal, read-only, mutation; idempotency/order-payment state/network |
| 05 Tra đơn/refund status | `order_lookup`, `refund_status` | EXP-LOOK-001/004 / 002/005 / 003 | read-only nhưng luôn kiểm ownership/token |
| 06 Refund request demo | `refund_request` | EXP-REF-001/004/007/009 / 002/005/008 / 003/006 | proposal và mutation; confirmation + refund-state negative matrix |
| 07 Chào hỏi | `greeting` | EXP-GREET-001 / 002 / 003 | read-only, không tool/token |
| 08 Out-of-scope/injection | `out_of_scope`, `prompt_injection` | EXP-SAFE-001/004 / 002/005 / 003 | read-only safe refusal; zero side effect |

Mỗi nhóm có ít nhất một direct, paraphrase và follow-up. Case history là dữ liệu
không tin cậy, chỉ hỗ trợ resolve ngữ cảnh; không cấp quyền hoặc thay confirmation.

## 5. Oracle status/error/action trọng yếu

| Tình huống | HTTP | Error code | Action | Side effect |
|---|---:|---|---|---|
| Read/proposal hợp lệ | 200 | `null` | service allow-list tương ứng | `none` hoặc `proposal_created` |
| Order/refund tạo mới hợp lệ | 201 | `null` | commit typed mutation | đúng một transaction |
| Cart version cũ | 409 | `CART_VERSION_CONFLICT` | reject stale cart | không đổi cart/version |
| Cùng idempotency key, payload khác | 409 | `IDEMPOTENCY_KEY_REUSED` | reject key reuse | không row/movement mới |
| Hủy order ở `shipping` | 409 | `ORDER_STATUS_NOT_CANCELLABLE` | reject transition | không status/stock change |
| Confirmation hết hạn | 409 | `CONFIRMATION_EXPIRED` | reject, tạo proposal mới | không business mutation |
| Confirmation đã dùng | 409 | `CONFIRMATION_ALREADY_USED` | reject replay | không business mutation thứ hai |
| Confirmation đổi payload | 409 | `CONFIRMATION_PAYLOAD_CHANGED` | reject | không business mutation |
| Resource đổi state | 409 | `ORDER_NOT_REFUND_ELIGIBLE` | revalidation reject | không refund request |
| Sai owner/resource/token | 404 | `RESOURCE_NOT_FOUND` | deny | không lộ data/side effect |
| Provider timeout | 200 | `null` | fallback | `status=provider_unavailable`; commerce API không ảnh hưởng |
| Ambiguous/prose confirmation | 200 | `null` | hỏi rõ hoặc out-of-scope | không proposal/token/mutation |

Các error code confirmation trong bảng là oracle đã khóa cho QA. Backend owner phải
đưa đúng các mã này vào OpenAPI trước implementation; thay đổi chỉ hợp lệ khi cập
nhật đồng bộ API contract, fixture, consumer và test, không parse message.

## 6. Risk và test-data plan

### 6.1. P0 risk controls

1. Route/injection sai: corpus direct/paraphrase/follow-up + closed allow-list +
   repository side-effect audit.
2. IDOR user/guest/admin: role × endpoint × owner; đổi ID/token; order code đơn lẻ
   và token của guest khác đều không đủ quyền.
3. Retry/concurrency: cùng key/payload, key conflict, last-stock race; đếm order,
   redemption và reserve/restore movement trong SQL.
4. State machine: decision table order/payment/refund; terminal/skip/reverse reject.
5. Confirmation: expired, consumed, wrong owner, changed payload và changed state;
   tất cả assert zero side effect.
6. Demo boundary: network/DNS recorder, dependency/config/credential scan và copy
   assertion; không gateway/bank/refund provider thật.
7. Grounding: source membership/current version + SQL hydration; adversarial model
   output không được dùng làm oracle.
8. Provider isolation: timeout/invalid output không làm hỏng catalog/cart/order;
   mutation không phụ thuộc Gemini để commit.
9. Contract drift: OpenAPI snapshot và frontend/RAG consumer type checks.
10. UI: 390×844 và 1366×768 tối thiểu, sau đó đủ viewport acceptance; console,
    page error, failed request và CTA overlap listener.

Risk machine-readable nằm trong `risk_register` của fixture. Mọi risk tiền, stock,
ownership, secret và grounding là P0 dù score số học thấp hơn.

### 6.2. Dataset `EXP_QA_BASE_V1`

- Identity: `admin_qa`, `user_a`, `user_b`, `guest_a`, `guest_b`; token guest chỉ
  sinh runtime, DB chỉ lưu hash; không fixture chứa secret/PII thật.
- Resource ổn định: cart A/B có version khác nhau; order A ở `completed` và
  `shipping`; guest order A; variant stock=1; payment/refund provider=`demo`.
- Price/amount/shipping/discount đều integer VND. Product/card current oracle lấy
  trực tiếp từ SQL sau mutation test, không hard-code theo vector.
- Confirmation fixture có clock cố định: valid, expired >5 phút, consumed,
  wrong-owner, payload-hash changed và resource-state changed.
- Idempotency fixture có owner/operation/resource scope, request hash và response
  snapshot; raw key/token không persist hoặc log.
- Invariant: owner mode XOR; một active cart/owner; reserve/restore unique theo
  order+movement type; một non-terminal refund/order; payment/refund external call=0.

Suite destructive chỉ chạy DB test khi opt-in reset rõ; migration/seed thiếu phải
FAIL/BLOCKED, không skip/pass ngầm. Mỗi mutation case kiểm row count trước/sau và
reset/namespace riêng để chạy lặp lại.

## 7. Entry, execution và exit

Entry: contract/OpenAPI/schema của slice đã khóa; migration/seed/reset command có
thật; provider stub deterministic; endpoint không còn placeholder. Nếu dependency
chưa có, giữ `planned` và không tạo test giả.

Thứ tự chạy: schema/fixture validator → unit decision tables → DB migration/seed →
integration transaction/concurrency → API contract/ownership → RAG corpus với stub
→ frontend desktop/mobile E2E → network/secret scan. Gemini smoke chỉ chạy khi có
credential ngoài repository và không thay provider stub.

Exit: mọi P0 applicable pass trên clean DB; không flaky/critical; exact command,
commit, counts và evidence được ghi. `SKIP` vì thiếu Gemini credential hoặc
`Planned` vì implementation chưa có không được gọi là PASS.
