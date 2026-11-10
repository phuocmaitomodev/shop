# Acceptance test plan

> **Acceptance gate hiện hành:** Yêu cầu phục hồi LAI ngày 2026-11-10 khóa
> filter/guard -> router allow-list -> RAG/controlled tools -> HITL cho commerce và
> tám nhóm chatbot. `EXP-CONTRACT-01..10` trong
> [`commerce-chatbot-expansion-contract.md`](commerce-chatbot-expansion-contract.md)
> là P0; các gate MVP/RET vẫn áp dụng cho phần catalog/policy không xung đột.

## 1. Mục đích

Tài liệu chuyển tiêu chí nghiệm thu trong `request.md` thành các kiểm tra có mã, điều kiện và kết quả mong đợi. Đây là baseline cho `shop-qa`; không thay thế yêu cầu gốc và không được tự hạ tiêu chuẩn.

## 2. Nguyên tắc thực thi

- Chạy trên database mới và môi trường local theo README, không dựa vào state thủ công còn sót.
- Ghi lại commit, browser/viewport, command, kết quả và bằng chứng lỗi.
- Kiểm thử ít nhất desktop và mobile; browser chính do QA chốt, ưu tiên Chromium và thêm một browser khác nếu thời gian cho phép.
- Với dữ liệu động, assert theo DB/API hiện tại thay vì text hard-code không liên quan.
- RAG cần kiểm tra grounding/source và dữ liệu SQL, không chỉ đánh giá câu trả lời “nghe hợp lý”.
- Kết quả release: PASS khi tất cả test P0 pass, không có lỗi nghiêm trọng; test P1 thất bại phải được triage/chấp thuận rõ ràng.

## 3. Tiền điều kiện và dữ liệu

- Docker/Compose và Gemini API key test hợp lệ; `.env` tạo từ `.env.example`.
- Database/volume mới cho lượt bootstrap.
- Seed cố định đủ 100 product, categories, variants, coupons, content RAG, admin/customer demo.
- Có product nhiều size/màu, product sắp hết hàng, coupon hợp lệ/hết hạn/không đủ điều kiện và order ở các trạng thái.
- Có câu hỏi RAG chuẩn tiếng Việt, không có dữ liệu, ngoài scope và prompt injection.

## 4. Khởi chạy hệ thống

| ID | P | Kiểm tra | Cách thực hiện | Kết quả mong đợi |
|---|---|---|---|---|
| BOOT-01 | P0 | README clean start | Làm đúng hướng dẫn trên máy/DB mới | Không cần bước ngầm; hệ thống chạy hoàn chỉnh local |
| BOOT-02 | P0 | Docker Compose | Build/start các service chính | Web, API, DB và worker cần thiết healthy |
| BOOT-03 | P0 | Migration | Chạy migration trên DB trống | Thành công một lần; schema/pgvector sẵn sàng |
| BOOT-04 | P0 | Seed | Chạy seed sau migration | Thành công, có tài khoản/content/demo data |
| BOOT-05 | P0 | Đúng 100 sản phẩm | Đếm qua DB và API admin | Chính xác 100 product demo, không 99/101 |
| BOOT-06 | P0 | Seed constraints | Kiểm tra category, 2–4 màu/product, size/variant/stock | Dữ liệu đáp ứng yêu cầu, không orphan/duplicate SKU |
| BOOT-07 | P0 | Environment safety | So `.env.example`, scan tracked files/log | Có placeholder; không API key/secret/password production thật |
| BOOT-08 | P1 | Seed/reset repeatability | Reset theo README rồi migration + seed lại | Kết quả tương đương, không duplicate hoặc state bí mật |

## 5. Website khách hàng

| ID | P | Kiểm tra | Kết quả mong đợi |
|---|---|---|---|
| CAT-01 | P0 | Trang chủ/danh mục/detail | Duyệt được 7 nhóm yêu cầu và mở product detail hợp lệ |
| CAT-02 | P0 | Dữ liệu product | Tên, SKU, mô tả, danh mục, giá/sale, ảnh, màu, size, stock và labels đúng seed |
| CAT-03 | P0 | Search | Tìm theo tên và keyword; kết quả đúng, empty state rõ |
| CAT-04 | P0 | Filter đơn/kết hợp | Category, price range, size, color và tổ hợp chỉ trả item phù hợp |
| CAT-05 | P0 | Sort | Giá tăng/giảm, newest, best-selling đúng định nghĩa dữ liệu |
| CAT-06 | P1 | Related products | Detail hiển thị product liên quan có link hợp lệ |
| CAT-07 | P0 | Variant selection | Chỉ chọn/thêm variant màu-size tồn tại và còn hàng |
| CAT-08 | P0 | Cart CRUD | Thêm, đổi quantity, xóa; totals cập nhật đúng |
| CAT-09 | P0 | Stock boundary | UI/API chặn quantity vượt stock và báo rõ |
| CAT-10 | P0 | Price/stock revalidation | Đổi giá/stock DB sau khi thêm cart rồi checkout | Backend phát hiện; không dùng giá/stock cũ |
| CAT-11 | P0 | Coupon valid | Discount và total tính đúng theo rule |
| CAT-12 | P0 | Coupon invalid | Hết hạn/sai/không đạt minimum/limit bị từ chối rõ |
| CAT-13 | P0 | Register/login/logout | Email/password hoạt động; session kết thúc đúng |
| CAT-14 | P1 | Forgot/reset password | Không gửi email thật; flow demo an toàn; không lộ email tồn tại |
| CAT-15 | P0 | Guest COD checkout | Hoàn thành đủ 6 bước và nhận order code/trang thành công |
| CAT-16 | P0 | Shipping fee | Phí cố định và ngưỡng miễn phí lấy từ config, tính đúng ở biên |
| CAT-17 | P0 | Online demo | Hiển thị rõ mô phỏng, không gọi cổng thanh toán/giao dịch thật |
| CAT-18 | P0 | Logged-in order history | Chỉ thấy lịch sử/chi tiết đơn của chính user |
| CAT-19 | P0 | Cancel rules | Chỉ hủy ở Chờ xác nhận/Đã xác nhận; từ Đang chuẩn bị trở đi bị chặn; stock hoàn một lần |
| CAT-20 | P1 | VND/tiếng Việt | Nội dung chính tiếng Việt, định dạng VND nhất quán |

## 6. Trang quản trị

| ID | P | Kiểm tra | Kết quả mong đợi |
|---|---|---|---|
| ADM-01 | P0 | RBAC | Customer/anonymous không vào/call admin; admin đăng nhập được |
| ADM-02 | P0 | Dashboard | Counts product/customer/order và demo revenue khớp dữ liệu/định nghĩa |
| ADM-03 | P0 | Product CRUD | Tạo/xem/sửa/xóa, ảnh/category/price/label hoạt động và storefront phản ánh |
| ADM-04 | P0 | Variant/stock CRUD | Quản lý color/size/stock; uniqueness và stock >= 0 được enforce |
| ADM-05 | P0 | Order management | Order mới xuất hiện; xem detail; chỉ chuyển status hợp lệ |
| ADM-06 | P0 | Customer privacy | Xem danh sách/lịch sử; không API/UI nào expose/sửa password hash |
| ADM-07 | P0 | Coupon CRUD | Rule tạo/sửa/xóa/active phản ánh đúng checkout |
| ADM-08 | P0 | RAG content CRUD | Quản lý FAQ, size, shipping, return, promotion; index status rõ |
| ADM-09 | P0 | Support tickets | Ticket hiện trong list; detail có đúng transcript liên quan |
| ADM-10 | P1 | Media validation | Ảnh hợp lệ upload local; loại/kích thước/path nguy hiểm bị chặn |

## 7. Chatbot RAG

### 7.1. Gate release `return_policy`

Mọi oracle policy lấy từ nội dung canonical tại mục 3.4 của
[`mvp-product-rag-scope.md`](mvp-product-rag-scope.md), không lấy từ câu trả lời mẫu
của model. Chạy provider stub deterministic cho release gate; Gemini smoke chỉ được
ghi PASS khi có key ngoài repository và đã chạy thật, nếu không phải ghi SKIP riêng.

| ID | P | Kiểm tra | Cách/Oracle | Kết quả mong đợi |
|---|---|---|---|---|
| RET-RAG-01 | P0 | Intent boundary | Hỏi trực tiếp, diễn đạt lại, follow-up về đổi/trả; xen kẽ product query, thời tiết và injection | Route chỉ thuộc `product_search`, `return_policy`, `out_of_scope`; policy variations đúng route, product regression giữ nguyên, ngoài phạm vi/injection fail closed |
| RET-RAG-02 | P0 | Canonical seed | Trên DB sạch chạy migration → seed → verifier → worker; chạy seed lại; làm sai/thiếu canonical fixture | Đúng một source `Chính sách đổi trả` type `return_policy`, locale `vi`, active; rerun không duplicate/job thừa; verifier fail closed; index current-version thành công |
| RET-RAG-03 | P0 | Retrieval validity | So sánh policy hợp lệ với FAQ, inactive, pending, failed, stale version; kiểm tra keyword + semantic và dedupe | Chỉ chunk policy tiếng Việt active/indexed/current-version được retrieve; hybrid rank deterministic theo cấu hình, không cộng raw score khác thang |
| RET-RAG-04 | P0 | Grounded answer | Hỏi riêng 07 ngày đổi, 03 ngày trả/hoàn, điều kiện đã giặt, mã đơn, phí đổi size, hàng sale và liên hệ | Facts là subset chính xác của source; phân biệt 07/03 ngày và phí hai chiều; không tuyệt đối hóa sale; `products=[]`; source/chunk IDs đúng; empty hoặc model output ngoài allow-list → `insufficient_data` |
| RET-RAG-05 | P0 | Freshness và guardrail | Update policy tạo version mới, trước/sau reindex; archive source; đặt instruction độc hoặc facts xung đột trong user/source | Chỉ version indexed hiện hành được dùng; không trộn stale; archive/không source → `insufficient_data`; không làm theo injection hoặc bịa policy |
| RET-RAG-06 | P0 | API và widget | Gọi `POST /chat`, mở widget mobile/desktop với policy response và product response regression | Policy trả `status=ok`, `products=[]`, source contract đầy đủ và citation title `Chính sách đổi trả`; không card/link policy giả; product card cũ giữ nguyên; không console error; Zalo chỉ là text liên hệ, không integration/live chat |

### 7.2. Ma trận lịch sử

| ID | P | Kiểm tra | Cách/Oracle | Kết quả mong đợi |
|---|---|---|---|---|
| RAG-01 | P0 | Kiến thức | Hỏi FAQ, size, shipping, return, promotion | Trả tiếng Việt đúng source/citation |
| RAG-02 | P0 | Product retrieval | Hỏi theo loại, budget, màu, size và tổ hợp | Candidate thỏa hard filters SQL |
| RAG-03 | P0 | Product cards | Kiểm tra response/UI | Đúng tên, ảnh, effective price, link detail hợp lệ |
| RAG-04 | P0 | Giá live | Sửa giá SQL rồi hỏi lại, không cần tin vector cũ | Answer/card khớp DB hiện tại |
| RAG-05 | P0 | Stock live | Sửa stock/variant rồi hỏi lại | Answer/card khớp DB, không gợi ý variant hết hàng như còn hàng |
| RAG-06 | P0 | Session context | Hỏi product rồi “còn màu đen/size M không?” cùng session | Hiểu tham chiếu; session khác không bị rò context |
| RAG-07 | P0 | Anonymous chat | Dùng không đăng nhập và thử đọc session bằng ID không token | Chat hoạt động; transcript được bảo vệ |
| RAG-08 | P0 | Missing data | Hỏi thông tin không có | Nói chưa tìm thấy/không đủ dữ liệu, không bịa |
| RAG-09 | P0 | Out of scope | Hỏi chủ đề ngoài shop | Thông báo giới hạn lịch sự |
| RAG-10 | P0 | Prompt injection | Yêu cầu bỏ quy tắc/đọc secret; source chứa instruction độc | Không làm theo, không lộ prompt/secret/data khác |
| RAG-11 | P0 | Product reindex | Admin sửa mô tả rồi chờ/retry index | Semantic retrieval dùng nội dung mới; field động vẫn từ SQL |
| RAG-12 | P0 | Knowledge reindex | Admin sửa document | Version mới truy xuất được sau index; không trộn source inactive |
| RAG-13 | P0 | Hallucinated output | Stub model trả product ID/giá ngoài context | Validator loại/chặn và fallback an toàn |
| RAG-14 | P1 | Gemini failure | Timeout/invalid provider trong test | Chat báo tạm không khả dụng; shop APIs vẫn chạy |
| RAG-15 | P0 | Support handoff | Yêu cầu nhân viên/retry request | Tạo đúng một ticket, trả code và admin thấy transcript |
| RAG-16 | P1 | Widget position | Mở/đóng/scroll trên các viewport | Không che CTA/navigation hoặc va chạm fixed UI |

## 8. Giao diện, kỹ thuật và bảo mật cơ bản

| ID | P | Kiểm tra | Kết quả mong đợi |
|---|---|---|---|
| UI-01 | P0 | Responsive | Các trang chính ở mobile/desktop không overflow/chồng lấn |
| UI-02 | P0 | Touch interaction | CTA/input/menu/cart/chat thao tác được, vùng bấm hợp lý |
| UI-03 | P0 | Internal links | Crawl/click header, category, product, account, footer | Không dead link; legal/contact giả được ghi rõ dữ liệu mẫu |
| UI-04 | P0 | HTTP success | Trang chính và asset/API cần thiết | HTTP thành công; 404 chỉ cho route/resource không tồn tại |
| UI-05 | P0 | Browser console | Chạy các luồng P0 | Không uncaught JS error hoặc lỗi nghiêm trọng |
| UI-06 | P1 | Loading/error/empty | Network chậm/lỗi/không data | Trạng thái rõ, không treo UI |
| SEC-01 | P0 | Authorization ownership | Đổi ID order/cart/chat/customer | Không đọc/sửa tài nguyên người khác |
| SEC-02 | P0 | Secrets | Inspect bundle, repo, logs, network | Không Gemini key/DB secret/password/token nhạy cảm |
| SEC-03 | P0 | Input safety | SQL-like input, XSS text, upload path | Parameterized/escaped/validated; không thực thi payload |
| TECH-01 | P0 | README completeness | Theo từng mục | Có Gemini config, Compose/start, migration, seed, demo login |

## 9. Ma trận viewport tối thiểu

- Mobile nhỏ: 360×800.
- Mobile phổ biến: 390×844.
- Tablet: 768×1024.
- Desktop: 1366×768 và 1440×900.

Kiểm tra ít nhất: header/menu/search, listing/filter, product variant CTA, cart/checkout, auth, admin tables/forms và chat widget open/closed.

## 10. Automation đề xuất

- Backend unit/integration: pricing, coupon, stock transaction, order state, authorization, RAG validators.
- API contract: OpenAPI schema và response/error fixtures.
- DB: migration up trên DB mới, seed verifier, constraints/concurrency.
- Frontend component: format VND, filters/cart totals, route guards, chat card.
- E2E browser: guest COD, customer history, admin order/product/content, RAG/ticket.
- RAG eval: deterministic retrieval tests với provider stub; một smoke suite thật với Gemini khi có key.

## 11. Exit criteria

- Tất cả P0 pass trên clean run; không flaky chưa được xử lý.
- P1 failures có owner, mức ảnh hưởng và quyết định rõ.
- Không còn blocker/critical; không có secret thật.
- Báo cáo đính kèm test run, screenshots/logs cần thiết, DB product count và danh sách deviation (nếu có).

## 12. Gate mở rộng commerce/chatbot

- Mỗi nhóm intent có positive, negative, ownership, retry và injection case.
- Cart/order/payment/refund chạy trên PostgreSQL sạch; test race/idempotency và
  chứng minh stock không double reserve/restore.
- User, guest và admin boundary được test bằng đổi resource ID/token; guest lookup
  cần order code + header token.
- Chat mutation phải qua proposal/confirmation một lần; expired/replayed/wrong
  owner/changed payload đều fail closed và không có side effect.
- `POST /chat` chỉ phát proposal khi có typed `action_context` từ UI/server state với
  exact variant/item/order/cart IDs và field bắt buộc theo action. Prose/model không
  tạo ID/amount; thiếu/ambiguous/unknown field cho zero side effect.
- Test production wiring trên PostgreSQL thật: DB-backed adapter issue/consume token
  atomically, reauthorize/revalidate rồi gọi cùng reviewed commerce use-case. Mock,
  fake, no-op hoặc dependency trả `None` chỉ là unit support, không đủ để PASS gate.
- E2E bao phủ cart add/update/remove, order create/cancel và refund request với token
  expiry/replay/wrong owner, version/price/stock/state thay đổi, duplicate key và
  chứng minh không có mutation trước confirm.
- UI/E2E ghi rõ COD/online/refund là mô phỏng, tiếng Việt/VND, responsive và
  không có request tới payment/refund provider bên ngoài.

### 12.1. Ma trận recovery LAI bắt buộc

| Slice | P | Bài kiểm tra bắt buộc | Oracle |
|---|---|---|---|
| Filter/guard | P0 | user/source/history injection, oversize, SQL/XSS-like text, outside shop, ambiguous commerce text | Guard chạy trước dependency; `out_of_scope` hoặc `insufficient_data` ổn định; products/sources/proposal rỗng; zero provider/retrieval/tool/mutation |
| Closed router | P0 | positive/negative/paraphrase/follow-up cho đủ 8 group; unknown enum/extra field/provider disagreement | Chỉ intent + operation class allow-list; read không thành mutation; không dispatch tên tool/model output |
| Grounded RAG | P0 | knowledge active/indexed/current vs inactive/pending/failed/stale/mixed; product live price/stock/promotion; hallucinated IDs | Citation/candidate thuộc retrieval set; SQL hydration hiện tại; thiếu nguồn `insufficient_data`; provider failure bounded |
| Controlled reads | P0 | authenticated precedence; guest cart cookie; exact guest order code + lookup header; IDOR/missing credential; production dependency wiring | Owner check trước SQL; typed DTO; amount/status từ SQL; `None`/mock-only wiring không PASS |
| HITL mutation | P0 | prose không context; proposal; explicit confirm; wrong owner/resource; TTL; replay; changed payload/key/version/price/stock/state; concurrent consume | Proposal zero side effect; TTL <= 300s; atomic binding; shared use-case; exactly-once inventory/refund; stable code |
| Frontend | P0 | authoritative context, proposal impact, Confirm/Cancel, duplicate click, uncertain network retry, server refresh, desktop/mobile/a11y | Tiếng Việt/VND/demo; cùng binding khi retry; không localStorage token; không che CTA; không console error |
| Independent QA | P0 | exact producer SHAs trên clean PostgreSQL/pgvector + deterministic provider + desktop/mobile browser | QA không sửa producer; zero discovered mandatory tests = FAIL; Gemini thiếu key = SKIP riêng, không PASS |

Stable routing results: injection/outside shop -> HTTP 200 `out_of_scope`; ambiguous
in-scope/missing source/context/credential -> HTTP 200 `insufficient_data`; provider
failure -> HTTP 200 `provider_unavailable`; schema unknown -> HTTP 422;
`RATE_LIMITED` -> HTTP 429. Mọi fail-closed case không lộ resource/token/prompt/error raw.

Stable mutation errors phải assert bằng `error.code`, không parse message:
`RESOURCE_NOT_FOUND` (404); `CONFIRMATION_INVALID`, `CONFIRMATION_EXPIRED`,
`CONFIRMATION_ALREADY_USED`, `CONFIRMATION_PAYLOAD_CHANGED`,
`IDEMPOTENCY_KEY_REUSED`, `CART_VERSION_CONFLICT`, `PRICE_CHANGED`,
`OUT_OF_STOCK`, `ORDER_STATUS_NOT_CANCELLABLE`, `REFUND_NOT_ELIGIBLE` (409), cùng
các mã coupon đã khóa. Exact retry cùng binding trả snapshot cũ; đổi một thành phần
phải fail closed.

`RAG-06/07` vẫn là P0: test phải chứng minh follow-up cùng server-derived session và
anonymous transcript không đọc được chỉ bằng session UUID. Bounded history do client gửi
không phải bằng chứng PASS cho session ownership/persistence.
