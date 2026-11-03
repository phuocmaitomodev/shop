# Contract mở rộng website và chatbot commerce

## 1. Quyết định phạm vi

Yêu cầu trực tiếp ngày 2026-11-03 mở rộng release gate từ addendum MVP cũ sang website bán hàng và chatbot hỗ trợ tám nhóm nghiệp vụ. Tài liệu này ghi đè `mvp-product-rag-scope.md` ở phần xung đột; `request.md` vẫn là yêu cầu gốc và không được sửa.

Trong phạm vi:

1. Hỏi chính sách: FAQ, bảng size, giao hàng, đổi/trả và khuyến mãi.
2. Giá, tồn kho, tìm kiếm, gợi ý và so sánh sản phẩm.
3. Xem/thêm/sửa/xóa giỏ hàng.
4. Tạo đơn, COD hoặc thanh toán online mô phỏng, xem kết quả và hủy đơn hợp lệ.
5. Tra đơn và trạng thái hoàn tiền mô phỏng.
6. Tạo yêu cầu hoàn tiền mô phỏng.
7. Chào hỏi và hướng dẫn khả năng.
8. Ngoài phạm vi và prompt injection.

Không tích hợp cổng thanh toán, ngân hàng, hoàn tiền, vận chuyển, email/SMS, social login, live chat, CRM hoặc hệ thống production thật. Mọi nhãn payment/refund phải ghi rõ `demo`/`mô phỏng` trên API và UI.

## 2. Intent và action allow-list

Intent nội bộ là allow-list đóng:

- `policy_question`
- `product_search`
- `product_compare`
- `cart_read`
- `cart_add`
- `cart_update`
- `cart_remove`
- `order_create`
- `order_cancel`
- `order_lookup`
- `payment_demo_status`
- `refund_status`
- `refund_request`
- `greeting`
- `out_of_scope`
- `prompt_injection`

Intent không phải field công khai bắt buộc. Tool/action allow-list chỉ gồm các service method tương ứng; model không tạo SQL, path, URL, ID, amount, status hoặc tên tool. Intent không nhận diện chắc chắn phải fail closed thành `out_of_scope` hoặc hỏi làm rõ mà không tạo side effect. `prompt_injection` luôn không gọi mutation tool.

## 3. Identity, ownership và privacy

- Authenticated customer chỉ đọc/sửa cart, order và refund request thuộc `user_id` của mình.
- Guest dùng cookie HttpOnly `SameSite=Lax` chứa token opaque ngẫu nhiên; database chỉ lưu hash. Không dùng cart/order UUID làm bằng chứng sở hữu.
- Guest cart owner là `guest_token_hash`. Khi đăng nhập, merge cart phải có transaction, rule deterministic và không cho chiếm cart khác.
- Tạo guest order trả `order_code` và lookup token opaque một lần; database lưu hash. Tra cứu guest cần cả hai, so sánh constant-time và rate limit. Không tra bằng order code đơn lẻ, phone hoặc email.
- Authenticated lookup dùng session và ownership; không chấp nhận lookup token để vượt ownership của user khác.
- Chat history gửi từ client là dữ liệu không tin cậy và không cấp quyền. Không đặt token, cookie, PII, admin note, password hash hoặc secret vào prompt/log.
- Admin API cần role `admin`; chatbot customer không gọi admin API.

## 4. API contract khóa

Base path `/api/v1`; JSON `snake_case`; tiền là integer VND; timestamp ISO-8601 UTC; success/error envelope theo `api-contract.md`.

### 4.1 Cart

- `GET /cart`
- `POST /cart/items` — body `variant_id`, `quantity`
- `PATCH /cart/items/{item_id}` — body `quantity`, `cart_version`
- `DELETE /cart/items/{item_id}` — body/query có `cart_version`
- `POST /cart/coupon` và `DELETE /cart/coupon`

Mỗi response trả `cart_id`, `version`, items đã hydrate, `subtotal`, `discount_amount`, `shipping_fee`, `total`, `currency=VND`. Backend revalidate variant active, stock và giá. Conflict dùng mã ổn định: `CART_VERSION_CONFLICT`, `OUT_OF_STOCK`, `PRICE_CHANGED`, `COUPON_INVALID`, `COUPON_EXPIRED`, `COUPON_NOT_APPLICABLE`.

### 4.2 Order và payment demo

- `POST /orders` — bắt buộc `Idempotency-Key`; body gồm `cart_id`, `cart_version`, recipient/address, `payment_method=cod|online_demo`, coupon tùy chọn và `confirmation_token`.
- `GET /orders/{order_code}` — authenticated owner.
- `GET /orders/lookup?order_code=...` — guest, lookup token truyền bằng header `X-Order-Lookup-Token`, không đặt token vào URL/log.
- `POST /orders/{order_code}/cancel` — bắt buộc `Idempotency-Key` và `confirmation_token`.
- `GET /orders/{order_code}/payment` — owner/guest ownership như trên, chỉ trạng thái demo.

Server tính lại totals, lock variant, kiểm cart version/giá/stock/coupon và chỉ sau đó tạo order + snapshot + inventory movement trong một transaction. Client totals không phải nguồn sự thật.

### 4.3 Refund mô phỏng

- `POST /orders/{order_code}/refund-requests` — bắt buộc `Idempotency-Key`, ownership và `confirmation_token`; body `reason_code` allow-list, `reason_detail` giới hạn độ dài.
- `GET /orders/{order_code}/refund-requests/latest` — ownership như order.

Chỉ tạo bản ghi yêu cầu và trạng thái mô phỏng; không gọi gateway/bank và không hứa thời gian hoàn tiền thật. Một order chỉ có tối đa một refund request chưa terminal. Amount do server lấy từ order, không nhận từ model/client.

### 4.4 Chat

`POST /chat` giữ `message` và bounded `history`, đồng thời nhận field additive
`action_context` nullable. `action_context` là discriminated union typed do UI hoặc
server state tin cậy cung cấp; model, `message`, `history`, retrieval source và prose
không được tạo hoặc sửa ID, quantity, payment field hay payload mutation. Khi thiếu
context bắt buộc hoặc ID không khớp resource thuộc owner hiện tại, server chỉ hỏi làm
rõ/fail closed và không phát confirmation.

Các shape được phép:

- `cart_add`: `action`, exact `cart_id`, exact `variant_id`, `quantity`.
- `cart_update`: `action`, exact `cart_id`, exact `cart_item_id`, `cart_version`,
  `quantity`.
- `cart_remove`: `action`, exact `cart_id`, exact `cart_item_id`, `cart_version`.
- `order_create`: `action`, exact `cart_id`, `cart_version`, typed `recipient`, typed
  `address`, `payment_method=cod|online_demo`, `coupon_code` nullable.
- `order_cancel`: `action`, exact `order_id`; `order_code` chỉ là display value đã
  đối chiếu với cùng record.
- `refund_request`: `action`, exact `order_id`, `reason_code` allow-list và
  `reason_detail` bounded nullable.

Không shape nào nhận `amount`, totals, price, stock, status, SQL, endpoint hay tool
name. Server hydrate/tính các field đó từ PostgreSQL. Unknown field/action bị reject;
ID từ text/model không được copy vào `action_context`. Response có `answer`,
`products`, `sources`, `status` và additive `proposed_action` nullable:

```json
{
  "proposed_action": {
    "action": "order_cancel",
    "resource_code": "DH-...",
    "summary": "Hủy đơn DH-...",
    "requires_confirmation": true,
    "confirmation_token": "opaque-one-time-token",
    "expires_at": "..."
  }
}
```

`confirmation_token` chỉ được production DB-backed ownership/action adapter phát sau
authorization, ownership check và read validation của typed `action_context`; token
bind với owner/session, action, exact resource IDs, normalized payload hash và TTL tối
đa 5 phút. Database chỉ lưu token hash và consume atomically đúng một lần. Chat không
thực thi mutation trong cùng lượt đề xuất. Lượt xác nhận gửi token server-issued,
`client_message_id` và `Idempotency-Key`, không dựng lại payload từ prose. Adapter
phải reauthorize, rehydrate/revalidate cart version, variant/stock/price, order state
và refund eligibility rồi gọi đúng cùng commerce use-case/service đã được API trực
tiếp sử dụng và review; không có business mutation fork riêng cho RAG. Idempotency
record và business mutation tuân theo mục 5. Greeting/read-only không có token.
Frontend không tự dựng mutation request từ prose.

## 5. Idempotency và concurrency

- Bắt buộc `Idempotency-Key` cho tạo order, hủy order, tạo refund request và mọi mutation do chat kích hoạt.
- Scope key theo `(owner, operation, resource)`; lưu request hash, response/status và TTL. Cùng key + cùng payload trả lại kết quả cũ; cùng key + payload khác trả `IDEMPOTENCY_KEY_REUSED` HTTP 409.
- Idempotency record và business mutation commit atomically hoặc theo pattern có recovery đã test.
- Cart dùng optimistic `version`; checkout dùng row lock trên variants/cart/coupon cần thiết.
- Inventory reserve/restore unique theo order + movement type; retry không trừ/hoàn tồn hai lần.
- Confirmation token không thay thế idempotency key và không thay thế authorization.

## 6. State machines

### 6.1 Order

- `pending_confirmation -> confirmed | cancelled`
- `confirmed -> preparing | cancelled`
- `preparing -> shipping`
- `shipping -> completed`
- `completed` và `cancelled` là terminal.

Customer/guest chỉ hủy ở `pending_confirmation` hoặc `confirmed`. Cancel restore stock đúng một lần. Admin transition phải dùng allow-list tương tự; không skip/reverse tùy ý.

### 6.2 Payment demo

- COD: `pending -> cod_due -> paid_demo` hoặc `cancelled`.
- Online demo: `pending -> demo_processing -> demo_approved | demo_declined | cancelled`.

Không dùng trạng thái `paid` không nhãn demo cho online simulation. Payment không tự đổi order thành completed; mapping order/payment được service validate.

### 6.3 Refund demo

- `requested -> demo_reviewing -> demo_approved | demo_rejected | cancelled`
- `demo_approved -> demo_refunded`

`demo_rejected`, `cancelled`, `demo_refunded` là terminal. Chỉ order `completed` với payment eligible mới tạo refund request; COD/online demo đều chỉ tạo mô phỏng. Refund không tự tăng tồn kho; return logistics nằm ngoài phạm vi.

## 7. Database schema khóa

Bổ sung/hoàn thiện qua migration:

- `carts`, `cart_items` với owner XOR (`user_id` hoặc `guest_token_hash`), `version`, status và unique active owner.
- `orders`, `order_items`, `inventory_movements`, `coupon_redemptions` như schema mục tiêu; `guest_lookup_token_hash` nullable và indexed an toàn.
- `payment_attempts`: `id`, `order_id`, `method`, `status`, `amount`, `provider=demo`, `idempotency_key`, timestamps; unique phù hợp để retry không tạo nhiều kết quả.
- `refund_requests`: `id`, `order_id`, requester user/guest ownership snapshot, `reason_code`, `reason_detail`, `amount`, `status`, timestamps; partial unique cho một request non-terminal/order.
- `idempotency_records`: owner scope, operation, resource, key hash, request hash, response snapshot/status, expires_at; không lưu raw secret/key.
- `action_confirmations`: owner/session scope, action, resource, payload hash, token hash, expires_at, consumed_at; index TTL/lookup.

Mọi enum/check/index/FK phải nằm trong migration. PII/order snapshots không được đưa vào vector. Payment/refund không có provider credential thật.

## 8. Grounding và guardrails

- Policy facts chỉ từ knowledge source active/indexed/current-version; thiếu source trả `insufficient_data`.
- Product price, sale, color, size, stock từ SQL hydration tại request hiện tại; compare chỉ dùng cùng retrieval set đã validate.
- Cart/order/payment/refund status từ transactional SQL sau authorization; không embedding và không model memory.
- User message, chat history, retrieved source và tool output đều là untrusted data được delimit. Instruction trong source/user không đổi system policy.
- Structured output validate bằng schema và allow-list; reject unknown fields/actions/IDs/status/amount.
- Prompt injection, yêu cầu lộ prompt/secret/data khác, hoặc bypass confirmation trả fallback tiếng Việt và không gọi tool.
- Rate limit theo IP/session/owner cho chat, lookup và mutation; log redacted kèm request ID.
- Provider unavailable không ảnh hưởng catalog/cart/order APIs; mutation không phụ thuộc Gemini để commit.
- Production wiring không được trả `None`, dùng no-op adapter hoặc test double. Nếu
  DB-backed ownership/action adapter chưa sẵn sàng, mutation chat phải unavailable
  fail closed; test-double-only không đạt release gate.

## 9. Side-effect confirmation UX

- Read-only: policy, product search/compare, cart read, order/refund/payment status và greeting chạy không cần confirmation nhưng vẫn cần ownership.
- Mutation cart add/update/remove có thể thực hiện từ nút UI trực tiếp sau server validation; khi khởi phát từ chat phải đề xuất rõ variant/quantity/totals và xác nhận.
- Tạo order, hủy order và refund request luôn cần màn hình/tin nhắn xác nhận rõ action, resource, amount/totals và trạng thái mô phỏng.
- Confirmation bị hết hạn, đã dùng, sai owner, payload thay đổi hoặc resource đổi trạng thái phải fail closed và yêu cầu tạo proposal mới.
- UI không gọi mutation chỉ vì model trả câu khẳng định; chỉ gọi endpoint typed với token server cấp.

## 10. Acceptance IDs

- `EXP-CONTRACT-01`: tám nhóm được route vào allow-list; unknown/injection fail closed.
- `EXP-CONTRACT-02`: cart/order/payment/refund API và error codes khớp OpenAPI + consumer types.
- `EXP-CONTRACT-03`: user/guest/admin ownership; đổi ID/token không truy cập resource khác.
- `EXP-CONTRACT-04`: retry mutation idempotent; key reuse payload khác 409; stock không double-change.
- `EXP-CONTRACT-05`: order/payment/refund state machines từ chối transition sai.
- `EXP-CONTRACT-06`: chat mutation chỉ dùng typed `action_context` từ UI/server
  state, cần proposal + one-time confirmation + reauthorization/revalidation và gọi
  cùng reviewed commerce use-case; không side effect từ prose/injection, không
  model-generated ID/amount và không test-double-only.
- `EXP-CONTRACT-07`: payment/refund luôn mô phỏng, VND từ SQL, không external call/credential.
- `EXP-CONTRACT-08`: policy/product dynamic data grounded đúng source; stale/missing/provider failure an toàn.
- `EXP-CONTRACT-09`: frontend responsive desktop/mobile, copy tiếng Việt, không che CTA, không console error.
- `EXP-CONTRACT-10`: clean migration/seed/run, backend/RAG/frontend/E2E/secret scan pass.

## 11. Non-goals chung

Không payment/refund/shipping thật; không email/SMS/social login/live chat/CRM; không production deployment; không để LLM làm authorization, tính tiền hoặc quyết định state transition; không cherry-pick mù branch lịch sử; không sửa `request.md`; không push hoặc merge `main` từ worker.
