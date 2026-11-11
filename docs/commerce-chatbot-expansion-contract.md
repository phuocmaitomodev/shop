# Contract mở rộng website và chatbot commerce

## 1. Quyết định phạm vi

Yêu cầu trực tiếp ngày 2026-11-10 khôi phục pipeline LAI theo thứ tự
`filter/guard -> router allow-list đóng -> RAG hoặc controlled tools -> HITL` là
release gate hiện hành. Nó tiếp tục quyết định mở rộng ngày 2026-11-03 và ghi đè
addendum MVP cũ trong `mvp-product-rag-scope.md` ở phần xung đột; `request.md` vẫn
là yêu cầu gốc và không được sửa. Baseline phục hồi là
`6cc1ad99ace66bfdb6e1f19f2d6f5a89c0b0ae2f`; branch EXP lịch sử chỉ là evidence,
không phải prerequisite có thể cherry-pick nguyên nhánh.

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

### 2.1. Pipeline LAI bắt buộc

Mỗi request đi qua đúng một chiều, không được nhảy stage:

1. **Filter/guard** chạy trước model/retrieval/tool. Nó giới hạn input/history,
   rate-limit, phát hiện user/source injection, đánh dấu mọi prose/history/source là
   untrusted và không được làm thay đổi policy. Injection hoặc yêu cầu ngoài shop trả
   `status=out_of_scope`, `products=[]`, `sources=[]`, `proposed_action=null` và gọi
   zero retrieval/tool/mutation. Input có vẻ thuộc shop nhưng thiếu/ambiguous action
   hoặc resource trả `status=insufficient_data` với câu hỏi làm rõ và cũng gọi zero
   side effect.
2. **Router allow-list đóng** chỉ trả một intent trong mục 2 và một operation class
   `rag_read | sql_read | mutation_proposal | greeting | reject`. Unknown enum,
   field thừa, output model sai schema hoặc router/model bất đồng đều fail closed;
   không dispatch bằng tên tool do model sinh.
3. **RAG hoặc controlled read tool** được chọn server-side. Allow-list nội bộ chỉ gồm
   `product_retrieve`, `knowledge_retrieve`, `cart_read`, `order_read`,
   `payment_demo_read`, `refund_demo_read`. Hai tool đầu trả candidate/source đã
   validate; bốn tool commerce derive owner trước query và trả typed DTO từ SQL.
   Model không nhận SQL, endpoint, credential hay quyền chọn resource ID.
4. **HITL mutation** chỉ bắt đầu khi request có `action_context` typed từ UI/server
   state tin cậy. Mutation prose không có context không được tạo proposal. Proposal
   luôn zero side effect; execution chỉ xảy ra ở request xác nhận riêng với token một
   lần, `client_message_id` và `Idempotency-Key` hợp lệ.

Read path và mutation path phải tách structurally. Không được để một provider call,
fallback hay generic tool executor tự chuyển read thành mutation.

### 2.2. Kết quả fail-closed ổn định

- `prompt_injection` và ngoài phạm vi: HTTP 200 với `status=out_of_scope`.
- In-scope nhưng thiếu source/context/credential hoặc ambiguous: HTTP 200 với
  `status=insufficient_data`; câu trả lời tiếng Việt nêu cần làm rõ, không giả PASS.
- Provider lỗi/timeout sau khi đã chọn RAG: HTTP 200 với
  `status=provider_unavailable`; commerce API và controlled SQL reads không phụ thuộc
  provider để commit.
- Schema request sai/unknown field: HTTP 422; rate limit: `RATE_LIMITED` HTTP 429.
- Không response fail-closed nào được chứa token, ID resource nước ngoài, raw provider
  error, system prompt hoặc chi tiết cho biết resource bị từ chối có tồn tại.

## 3. Identity, ownership và privacy

- Owner được derive server-side trước mọi read/proposal/confirmation. Model,
  `message`, `history`, retrieval source, `action_context` và ID client gửi lên không
  phải bằng chứng quyền.
- Authenticated session hợp lệ luôn có precedence; customer chỉ đọc/sửa cart, order,
  payment demo và refund request thuộc `user_id` của mình. Server không fallback sang
  guest credential khi session không sở hữu resource.
- Guest cart chỉ dùng cookie HttpOnly `SameSite=Lax` chứa token opaque ngẫu nhiên;
  database chỉ lưu hash. Không nhận cart token từ prose/body/header tùy ý và không dùng
  cart/order UUID làm bằng chứng sở hữu.
- Guest cart owner là `guest_token_hash`. Khi đăng nhập, merge cart phải có transaction, rule deterministic và không cho chiếm cart khác.
- Tạo guest order trả `order_code` và lookup token opaque một lần; database lưu hash.
  Mọi read/proposal/confirmation guest trên order, payment demo hoặc refund cần exact
  `order_code` của request cùng `X-Order-Lookup-Token`; so sánh hash constant-time và
  rate limit. Không tra bằng order code đơn lẻ, UUID, phone, email hoặc token trong URL/log.
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
`products`, `sources`, `status`, additive `proposed_action` nullable và additive
`action_result` nullable:

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

`action_result` chỉ xuất hiện sau successful confirmation và là strict server-produced
discriminated union: order create/cancel trả `{action, order: OrderResponse}`, refund
request trả `{action, refund: RefundResponse}`. Frontend phải dùng resource
authoritative này thay vì parse ID/credential từ `answer` hoặc proposal. Chỉ guest
`order_create` được trả `order.guest_lookup_token` một lần; exact retry trả cùng order
nhưng token `null`. Không action nào khác được expose lookup credential/secret.
Proposal, read, reject, error và cart mutation có `action_result=null`; client lấy
authoritative cart snapshot qua `GET /api/v1/cart` cho đến khi cart mutation và replay
snapshot có thể được lưu atomically trong cùng transaction idempotency.

`confirmation_token` chỉ được production DB-backed ownership/action adapter phát sau
authorization, ownership check và read validation của typed `action_context`; token
bind với owner/session, action, exact resource IDs, normalized payload hash và TTL tối
đa 5 phút. Database chỉ lưu token hash và consume atomically đúng một lần. Chat không
thực thi mutation trong cùng lượt đề xuất. Lượt xác nhận gửi token server-issued,
`client_message_id` và `Idempotency-Key`, không dựng lại payload từ prose. Adapter
phải khóa row confirmation và bind atomically cả `client_message_id` lẫn hash của
`Idempotency-Key` trước mọi mutation attempt; retry chỉ hợp lệ khi cả hai giá trị
khớp binding, còn partial binding hoặc thay một trong hai phải fail closed. Adapter
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
  DB-backed ownership/read/action adapter chưa sẵn sàng, controlled read trả
  `insufficient_data` và mutation chat phải unavailable fail closed; test-double-only
  không đạt release gate. Compatibility endpoint có dependency seam trả `None` chỉ là
  baseline gap, không phải production implementation.
- Context nối tiếp và anonymous isolation theo `RAG-06/07` là P0: client-supplied
  bounded history có thể là input untrusted nhưng không thay thế server-derived session
  ownership. Session/transcript chỉ đọc được bằng authenticated owner hoặc anonymous
  secret token hash; session UUID đơn lẻ không cấp quyền.

## 9. Side-effect confirmation UX

- Read-only: policy, product search/compare, cart read, order/refund/payment status và greeting chạy không cần confirmation nhưng vẫn cần ownership.
- Mutation cart add/update/remove có thể thực hiện từ nút UI trực tiếp sau server validation; khi khởi phát từ chat phải đề xuất rõ variant/quantity/totals và xác nhận.
- Tạo order, hủy order và refund request luôn cần màn hình/tin nhắn xác nhận rõ action, resource, amount/totals và trạng thái mô phỏng.
- Confirmation bị hết hạn, đã dùng, sai owner, payload thay đổi hoặc resource đổi trạng thái phải fail closed và yêu cầu tạo proposal mới.
- UI không gọi mutation chỉ vì model trả câu khẳng định; chỉ gọi endpoint typed với token server cấp.

## 10. Sáu recovery slice và dependency freeze

| Slice | Owner chính | Contract khóa | Gate |
|---|---|---|---|
| 1. Filter/guard | `shop-rag` | Chạy trước provider/retrieval/tool; injection/out-of-scope/oversize/ambiguous fail closed và zero call | `EXP-CONTRACT-01/06/08/10`, `RAG-08..10/13`, `SEC-03` |
| 2. Closed router | `shop-rag` | Intent + operation class enum đóng; read và mutation tách; unknown/model disagreement không dispatch | `EXP-CONTRACT-01/06`, `RAG-09/10/13` |
| 3. Grounded RAG + controlled reads | `shop-rag` + `shop-backend` | Knowledge active/indexed/current; product live SQL hydration; owner-first cart/order/payment/refund DTO; production adapter không `None` | `EXP-CONTRACT-02/03/07/08`, `RAG-01..14`, `SEC-01` |
| 4. Proposal/confirmation HITL | `shop-backend` | Typed `action_context`; zero-side-effect proposal; token one-time TTL <= 5 phút; atomic binding, reauthorization/revalidation, shared use-case | `EXP-CONTRACT-03..07/10`, `SEC-01..03` |
| 5. Frontend tiếng Việt responsive | `shop-frontend` | Context từ state authoritative; impact + Confirm/Cancel; retry cùng binding; refresh server state; VND/demo; không che CTA | `EXP-CONTRACT-04..10`, `UI-01..06`, `SEC-02` |
| 6. Clean-room QA độc lập | `shop-qa` | Review exact SHA; PostgreSQL/pgvector sạch; deterministic provider; desktop/mobile; concurrency/exactly-once; secret/external-call scan | `EXP-CONTRACT-01..10`, `RAG-01..14`, `SEC-01..03` |

Dependency cứng: contract -> filter/guard + router -> grounded RAG/controlled reads ->
HITL backend -> frontend -> independent QA -> release integration. Frontend có thể
chuẩn bị component theo contract nhưng không PASS trước producer thật; QA không sửa
producer worktree. Mọi behavior change dùng TDD. Worker được commit task branch sạch
nhưng không push/merge/rebase `main` hoặc rewrite history.

### 10.1. Audit patch-equivalence tại baseline

`git cherry 6cc1ad99... <tip>` và inspection diff được dùng để phân biệt patch đã có
trên main với branch lịch sử. “Semantic present” không đồng nghĩa branch có thể
cherry-pick; gap production vẫn phải được test lại trên baseline.

| Historical SHA | Merge-base với baseline | Worktree lúc audit | Patch-equivalence/gap | Disposition |
|---|---|---|---|---|
| `54b8b3a01f2cb0e3d1fd1c39539dcfaa570a2cda` | `6a13a90640ab1be21206f5c202d1f5630b7e2631` | sạch | `git cherry` là `+`; patch-id `6b3db275...`; thêm ownership read và knowledge contract nhưng dùng `EXP-CONTRACT-11/12` ngoài gate hiện hành | Chỉ port semantics đã khóa trong 01..10; không cherry-pick |
| `a0c12c03df211497292f0fc4f4b0a28870e64b43` | `be81a61ff5664b46004c8d645d12732ff38c2ab3` | sạch | `git cherry` là `+`, nhưng strict guest order-code/token và intent hardening đã hiện diện semantically trên main; default controlled-read dependencies vẫn `None` | Reference cho slice 1–3; reimplement/test trên baseline |
| `ff62de50fae3ff1c4a641818445cdf01409f2491` | `be81a61ff5664b46004c8d645d12732ff38c2ab3` | sạch | `git cherry` là `-`; patch-id `44f3d2d5...`; binding `client_message_id` + hash `Idempotency-Key` đã patch-equivalent trên main | Không port lại; giữ làm oracle concurrency |
| `b019a8435645e6abffb73c3ed516b7343732e23c` | `be81a61ff5664b46004c8d645d12732ff38c2ab3` | sạch | `git cherry` là `-`; cùng patch-id `44f3d2d5...` với `ff62de5`, nhưng branch kéo theo tail RAG lịch sử | Duplicate evidence; tuyệt đối không cherry-pick tail |
| `49b55230ef4786d11e6654b3c6e9474e6882ab91` | `6a13a90640ab1be21206f5c202d1f5630b7e2631` | dirty, có FE edits/untracked tests ngoài commit | Commit có cùng patch-id `6b3db275...` với `54b8b3a`; `git cherry` là `+`; dirty state không phải evidence | Không dùng worktree; chỉ đối chiếu immutable commit |
| `195dbbe6aecad620569b60f750b965902ba7d2f9` | `be81a61ff5664b46004c8d645d12732ff38c2ab3` | dirty, có QA E2E/report ngoài commit | `git cherry` là `-`; fixture/validator 10 acceptance ID đã patch-equivalent trên main, nhưng chỉ chứng minh contract corpus planned | Giữ fixture làm oracle; clean-room QA mới quyết định PASS |

Kết luận audit: không SHA lịch sử nào được cherry-pick nguyên branch. Hai cặp duplicate
(`54b8b3a`/`49b5523`, `ff62de5`/`b019a84`) chỉ được tính một patch; dirty/untracked
artifact không được đưa vào handoff nếu chưa review và commit riêng.

## 11. Stable mutation errors

- `RESOURCE_NOT_FOUND` HTTP 404 cho resource không thuộc owner, không phân biệt absent/foreign.
- `CONFIRMATION_INVALID`, `CONFIRMATION_EXPIRED`,
  `CONFIRMATION_ALREADY_USED`, `CONFIRMATION_PAYLOAD_CHANGED` HTTP 409 cho token
  tương ứng; exact retry cùng owner/payload/`client_message_id`/key trả snapshot cũ,
  còn binding khác trả `IDEMPOTENCY_KEY_REUSED` HTTP 409.
- Revalidation dùng mã nghiệp vụ hiện có:
  `CART_VERSION_CONFLICT`, `PRICE_CHANGED`, `OUT_OF_STOCK`,
  `ORDER_STATUS_NOT_CANCELLABLE`, `REFUND_NOT_ELIGIBLE`,
  `COUPON_INVALID`, `COUPON_EXPIRED`, `COUPON_NOT_APPLICABLE`.
- Backend có thể map mã nội bộ cụ thể sang `RESOURCE_NOT_FOUND` ở public chat boundary
  để chống enumeration; frontend chỉ dựa vào `error.code`, không parse message.

## 12. Acceptance IDs

- `EXP-CONTRACT-01`: tám nhóm đi qua filter/guard rồi router allow-list đóng;
  unknown/injection/ambiguous không gọi retrieval/tool/mutation và trả status ổn định.
- `EXP-CONTRACT-02`: cart/order/payment/refund API và error codes khớp OpenAPI + consumer types.
- `EXP-CONTRACT-03`: user/guest/admin ownership server-derived; authenticated precedence;
  guest cart cookie và guest order code + lookup header; đổi ID/token không truy cập resource khác.
- `EXP-CONTRACT-04`: retry mutation idempotent; key reuse payload khác 409; stock không double-change.
- `EXP-CONTRACT-05`: order/payment/refund state machines từ chối transition sai.
- `EXP-CONTRACT-06`: chat mutation chỉ dùng typed `action_context` từ UI/server
  state, cần proposal + one-time confirmation + reauthorization/revalidation và gọi
  cùng reviewed commerce use-case; không side effect từ prose/injection, không
  model-generated ID/amount và không test-double-only.
- `EXP-CONTRACT-07`: payment/refund luôn mô phỏng, VND từ SQL, không external call/credential.
- `EXP-CONTRACT-08`: knowledge active/indexed/current, product và commerce reads hydrate
  SQL sau authorization; stale/missing/provider failure an toàn; session isolation đạt RAG-06/07.
- `EXP-CONTRACT-09`: frontend responsive desktop/mobile, copy tiếng Việt, không che CTA, không console error.
- `EXP-CONTRACT-10`: clean migration/seed/run, backend/RAG/frontend/E2E/secret scan pass.

## 13. Non-goals chung

Không payment/refund/shipping thật; không email/SMS/social login/live chat/CRM; không production deployment; không để LLM làm authorization, tính tiền hoặc quyết định state transition; không cherry-pick mù branch lịch sử; không sửa `request.md`; không push hoặc merge `main` từ worker.
