# Phạm vi MVP catalog và chat RAG sản phẩm

## 1. Quyết định phạm vi

Theo quyết định trực tiếp của người dùng ngày 2026-10-26, bản demo được thu gọn thành một vertical slice duy nhất:

1. Danh sách sản phẩm công khai.
2. Trang chi tiết sản phẩm tối giản.
3. Chat RAG tiếng Việt hỗ trợ tìm hiểu và lựa chọn sản phẩm.

`request.md` được giữ nguyên để bảo toàn yêu cầu gốc. Tài liệu này là addendum có ưu tiên cao hơn các tài liệu kế hoạch cũ đối với phần implementation và nghiệm thu MVP hiện tại. Những hạng mục bị loại khỏi MVP không được coi là lỗi hay blocker của bản demo thu gọn.

## 2. Mục tiêu người dùng

Khách không cần đăng nhập có thể:

- xem danh sách sản phẩm;
- tìm theo tên hoặc từ khóa cơ bản;
- mở trang chi tiết tối giản;
- hỏi chatbot bằng tiếng Việt về loại sản phẩm, ngân sách, màu, size, mô tả, giá và tình trạng còn hàng;
- nhận câu trả lời có căn cứ kèm product card và link nội bộ hợp lệ.

## 3. Trong phạm vi

### 3.1. Catalog công khai

- PostgreSQL là nguồn dữ liệu chuẩn.
- Seed xác định được gồm tối thiểu 20 sản phẩm demo thuộc ít nhất 4 danh mục, có mô tả, ảnh hoặc placeholder nội bộ, giá, màu, size và tồn kho.
- API danh sách có pagination, tìm theo tên/từ khóa và các filter tối thiểu: danh mục, khoảng giá, màu, size.
- API chi tiết theo slug trả thông tin hiển thị và các variant hiện có.
- Storefront có trang danh sách responsive và trang chi tiết tối giản.
- Không có giỏ hàng hoặc CTA mua hàng; CTA chính là xem chi tiết và hỏi chatbot.

### 3.2. Chat RAG sản phẩm

- Chỉ trả lời trong phạm vi sản phẩm đang có trong catalog.
- Product projection dùng tên, danh mục và mô tả để semantic retrieval.
- Category, budget, color và size là hard filters từ SQL khi người dùng nêu rõ.
- Giá, màu, size và tồn kho luôn được hydrate lại từ PostgreSQL tại thời điểm trả lời; không tin dữ liệu động từ vector hoặc lời sinh của model.
- Câu trả lời tiếng Việt có source/product IDs đã được validate, product cards và link `/san-pham/{slug}` hợp lệ.
- Có fallback rõ ràng khi không đủ dữ liệu, ngoài phạm vi hoặc provider lỗi.
- Chống prompt injection và không để model tạo product ID, giá hoặc tồn kho ngoài context đã xác thực.
- Gemini model và embedding model cấu hình qua biến môi trường; provider stub deterministic vẫn dùng cho test/local không có key.
- Reindex sản phẩm thực hiện bằng seed/index command hoặc worker hiện có; không cần giao diện quản trị.

### 3.3. Context hội thoại tối giản

- Không lưu transcript hoặc PII lâu dài ở server trong MVP.
- Frontend giữ một cửa sổ hội thoại ngắn trong bộ nhớ trình duyệt; API chỉ nhận số lượt gần nhất có giới hạn và validate kích thước.
- Reload trang có thể bắt đầu phiên mới. Không có support handoff.

## 4. Ngoài phạm vi

Các hạng mục sau bị loại khỏi MVP hiện tại:

- đăng ký, đăng nhập, refresh token, forgot/reset password và RBAC;
- cart, coupon, shipping fee, checkout, payment demo, order, inventory movement và order history;
- trang quản trị, dashboard và mọi CRUD admin;
- upload/quản lý media; chỉ dùng URL hoặc placeholder demo an toàn;
- quản lý FAQ, shipping, return, promotion và knowledge documents tổng quát;
- support ticket, live-agent handoff và transcript persistence;
- email/SMS/social login, thanh toán hoặc vận chuyển thật;
- best-selling, related products, media upload và các báo cáo nghiệp vụ;
- yêu cầu seed đúng 100 sản phẩm; MVP dùng tối thiểu 20 sản phẩm demo xác định được.

Code nền đã tồn tại cho các hạng mục ngoài phạm vi có thể được giữ nếu không cản build/test, nhưng không được mở rộng và không nằm trong release gate MVP.

## 5. Contract tối thiểu

### `GET /api/v1/products`

Query tối thiểu:

- `page`, `page_size`;
- `q`;
- `category`;
- `min_price`, `max_price`;
- `color`, `size`.

Response phải có `items` và metadata pagination. Mỗi item có tối thiểu: `id`, `slug`, `name`, `category`, `image_url`, `effective_price`, `available_colors`, `available_sizes`, `in_stock`.

### `GET /api/v1/products/{slug}`

Trả thông tin card cộng mô tả và danh sách variant gồm màu, size, stock. Không expose dữ liệu nội bộ hoặc trường quản trị.

### `POST /api/v1/chat`

Request tối thiểu:

- `message`;
- `history` tùy chọn, có giới hạn số lượt và độ dài.

Response tối thiểu:

- `answer`;
- `products` là danh sách card đã hydrate và validate từ SQL;
- `sources` là product IDs/chunk IDs hợp lệ;
- `status` phân biệt `ok`, `insufficient_data`, `out_of_scope`, `provider_unavailable`.

Mã lỗi dùng error envelope hiện hành. Không trả prompt hệ thống, secret hoặc raw provider response.

## 6. Acceptance gate MVP

| ID | Gate P0 | Kết quả mong đợi |
|---|---|---|
| MVP-BOOT-01 | Clean start | Compose, migration và seed/index command chạy được từ môi trường sạch. |
| MVP-CAT-01 | Danh sách | Trang và API hiển thị đúng dữ liệu seed, pagination và empty/error state. |
| MVP-CAT-02 | Filter/search | Tên/từ khóa, danh mục, giá, màu và size chỉ trả sản phẩm phù hợp. |
| MVP-CAT-03 | Chi tiết | Link nội bộ mở đúng slug; giá, variant và stock khớp PostgreSQL. |
| MVP-RAG-01 | Product retrieval | Câu hỏi loại/budget/màu/size trả candidate thỏa hard filters. |
| MVP-RAG-02 | Grounding | Answer, sources và product cards chỉ tham chiếu sản phẩm trong retrieval set. |
| MVP-RAG-03 | Live hydration | Sửa giá/stock trong SQL rồi hỏi lại; response phản ánh dữ liệu hiện tại mà không cần tin vector cũ. |
| MVP-RAG-04 | Guardrails | Missing data, ngoài phạm vi và prompt injection có fallback an toàn, không bịa. |
| MVP-RAG-05 | Provider behavior | Stub test deterministic pass; Gemini smoke pass khi có key, lỗi provider không làm catalog hỏng. |
| MVP-UI-01 | Responsive | Listing, detail và widget chat dùng được tại 390×844 và 1366×768, không che CTA. |
| MVP-TECH-01 | Build/test/security | Backend tests, frontend tests/build, link/console smoke và secret scan pass. |

## 7. Critical path thu gọn

```text
MVP-01 catalog API + deterministic seed
  ├─ MVP-02 product projection + indexing/provider
  ├─ MVP-03 product listing/detail UI
  └─ MVP-04 SQL/vector retrieval + live hydration
          ↓
      MVP-05 chat API + guardrails + Gemini structured output
          ↓
      MVP-06 chat widget + product cards
          ↓
      MVP-07 clean-room E2E và README
```

Mỗi task chỉ được hoàn tất khi có commit riêng, worktree sạch, test thực tế và handoff theo `AGENTS.md`. Worker không push hoặc merge; người dùng tạo PR vào `main`.

## 8. Definition of Done

MVP hoàn tất khi:

- ba màn hình/trạng thái chính hoạt động: listing, detail và chat widget;
- ba endpoint tối thiểu tuân thủ contract;
- dữ liệu catalog và field động của chat lấy từ PostgreSQL;
- semantic retrieval và Gemini/stub không bịa product ID hoặc dữ liệu động;
- toàn bộ gate P0 ở mục 6 pass trên clean run;
- README mô tả đúng lệnh migration, seed/index, start, test và cấu hình Gemini;
- không có secret thật hoặc lỗi nghiêm trọng trong browser console/log.
