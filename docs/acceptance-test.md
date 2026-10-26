# Acceptance test plan

> **Acceptance gate MVP hiện hành:** Chỉ các gate `MVP-*` trong [`mvp-product-rag-scope.md`](mvp-product-rag-scope.md) quyết định release bản thu gọn. Các test CAT/ADM/RAG/SEC cũ dưới đây được giữ để truy vết yêu cầu gốc và chỉ áp dụng khi nằm trong mapping MVP; hạng mục auth, cart, checkout, order, admin và support không còn là blocker.

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
