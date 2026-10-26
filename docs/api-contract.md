# API contract frontend ↔ backend

> **Contract MVP hiện hành:** Surface bắt buộc được thu gọn còn `GET /api/v1/products`, `GET /api/v1/products/{slug}` và `POST /api/v1/chat` như định nghĩa trong [`mvp-product-rag-scope.md`](mvp-product-rag-scope.md). Các nhóm API auth/cart/order/admin/support dưới đây được giữ làm contract mục tiêu lịch sử và không thuộc release gate MVP.

## 1. Quy ước chung

- Base path: `/api/v1`.
- JSON dùng `snake_case`; thời gian ISO-8601 UTC; tiền là số nguyên VND, không dùng float.
- ID nội bộ dùng UUID; mã public (`order_code`, `ticket_code`, SKU) là chuỗi ổn định.
- Danh sách dùng `page`, `page_size`; response gồm `items`, `page`, `page_size`, `total`.
- Sort dùng giá trị allow-list, ví dụ `price_asc`, `price_desc`, `newest`, `best_selling`.
- Mutation hỗ trợ/đòi `Idempotency-Key` ở checkout và tạo support ticket.
- Auth qua cookie HttpOnly theo kiến trúc; frontend gửi credentials. API không bao giờ trả password hash/token reset.
- OpenAPI sinh từ FastAPI là contract có thể máy kiểm tra; tài liệu này xác định nhóm API và semantics.

### Success envelope

Resource đơn có thể trả trực tiếp trong `data`; danh sách trả metadata:

```json
{"data": {}, "meta": {"request_id": "..."}}
```

### Error envelope

```json
{
  "error": {
    "code": "OUT_OF_STOCK",
    "message": "Sản phẩm không đủ tồn kho.",
    "fields": {"items.0.quantity": "Tối đa 2"},
    "details": {"variant_id": "...", "available": 2}
  },
  "meta": {"request_id": "..."}
}
```

Frontend dựa vào `code`, không parse `message`. Mã trạng thái chính: `400` validation nghiệp vụ, `401`, `403`, `404`, `409` conflict/stock/version, `422` schema validation, `429`, `503` dependency unavailable.

## 2. Auth và tài khoản

| Method | Path | Quyền | Mục đích |
|---|---|---|---|
| POST | `/auth/register` | Public | Tạo customer |
| POST | `/auth/login` | Public | Login email/password |
| POST | `/auth/refresh` | Cookie refresh | Cấp access mới |
| POST | `/auth/logout` | Auth | Thu hồi session/cookie |
| POST | `/auth/forgot-password` | Public | Tạo flow reset, response không lộ email tồn tại |
| POST | `/auth/reset-password` | Token | Đặt password mới |
| GET | `/auth/me` | Auth | User và role hiện tại |
| GET/PATCH | `/account/profile` | Customer | Xem/sửa hồ sơ |
| GET | `/account/orders` | Customer | Lịch sử đơn của chính user |
| GET | `/account/orders/{order_code}` | Customer | Chi tiết đơn thuộc user |
| POST | `/account/orders/{order_code}/cancel` | Customer | Hủy nếu trạng thái cho phép |

Login admin dùng cùng endpoint nhưng backend trả role; frontend điều hướng theo role. Không có social login.

Trong chế độ demo local, `forgot-password` luôn trả cùng một response và tạo token reset ngắn hạn nhưng API không trả token trong JSON và không gửi email thật. Người vận hành local lấy token bằng CLI được mô tả trong backend README. `reset-password` nhận `token` và `new_password`, dùng token một lần rồi thu hồi toàn bộ session hiện tại của user.

## 3. Catalog public

| Method | Path | Mục đích |
|---|---|---|
| GET | `/categories` | Danh mục active |
| GET | `/catalog/facets` | Size, màu, khoảng giá và facet counts |
| GET | `/products` | Search/filter/sort/pagination |
| GET | `/products/{slug}` | Chi tiết, images, labels, variants/stock availability |
| GET | `/products/{slug}/related` | Sản phẩm liên quan |

`GET /products` hỗ trợ: `q`, `category`, `min_price`, `max_price`, `sizes[]`, `colors[]`, `labels[]`, `sort`, `page`, `page_size`. Chỉ variant active/còn phù hợp tham gia filter availability. `effective_price` do backend tính từ `price`/`sale_price` hợp lệ.

Phạm vi BE-05 cung cấp `page`, `page_size`, danh sách category active, product card cơ bản và product detail theo slug. Các query search/filter/sort, facets và related trong contract trên được triển khai ở BE-07. Public API không trả product/category bị inactive hoặc soft-delete; detail chỉ trả variant active và vẫn giữ variant active có tồn kho bằng 0 để client hiển thị trạng thái hết hàng.

Product card tối thiểu:

```json
{
  "id": "uuid",
  "slug": "ao-thun-basic",
  "sku": "AT-001",
  "name": "Áo thun basic",
  "image_url": "/media/products/...",
  "price": 299000,
  "sale_price": 249000,
  "effective_price": 249000,
  "labels": ["Mới"],
  "available_sizes": ["S", "M", "L"],
  "available_colors": [{"id": "uuid", "name": "Đen", "hex_code": "#000000"}]
}
```

## 4. Cart, coupon và checkout

| Method | Path | Mục đích |
|---|---|---|
| GET | `/cart` | Cart theo user hoặc guest session |
| POST | `/cart/items` | Thêm `variant_id`, `quantity` |
| PATCH | `/cart/items/{item_id}` | Đổi quantity |
| DELETE | `/cart/items/{item_id}` | Xóa item |
| POST | `/cart/coupon` | Validate/apply code và trả totals mới |
| DELETE | `/cart/coupon` | Gỡ coupon |
| GET | `/checkout/shipping-quote` | Phí cố định/miễn phí theo subtotal |
| POST | `/orders` | Revalidate và tạo order |
| GET | `/orders/lookup` | Guest tra cứu bằng order code + verification token phù hợp |

Request tạo order chứa `cart_id`, `cart_version`, recipient/address, `payment_method` (`cod` hoặc `online_demo`) và coupon code nếu có. Không nhận totals do client làm nguồn sự thật. Response trả snapshot totals, `order_code`, status, payment simulation status và URL trang thành công.

Conflict quan trọng:

- `CART_VERSION_CONFLICT`
- `PRICE_CHANGED`
- `OUT_OF_STOCK`
- `COUPON_INVALID`, `COUPON_EXPIRED`, `COUPON_NOT_APPLICABLE`
- `ORDER_STATUS_NOT_CANCELLABLE`

API trả chi tiết item/giá mới để frontend yêu cầu user xác nhận lại khi cần.

## 5. Chat và support

### Contract MVP hiện hành

`POST /chat` là endpoint chat công khai, không lưu transcript. Request gồm
`message` (1–1000 ký tự, không chỉ có khoảng trắng) và tối đa 6 phần tử `history`;
mỗi phần tử có `role` (`user` hoặc `assistant`) và `content` 1–1000 ký tự.

Response dùng success envelope và trả `answer`, `products`, `sources`, `status`.
`status` thuộc `ok`, `insufficient_data`, `out_of_scope`, `provider_unavailable`.
Product card và source ID chỉ được tạo từ retrieval set đã hydrate lại bằng SQL;
link sản phẩm có dạng `/san-pham/{slug}`. Endpoint không tạo session, ticket hoặc
lưu lịch sử. Các endpoint session/support bên dưới là contract lịch sử ngoài MVP.
Endpoint áp dụng rate limit theo IP và trả error envelope `RATE_LIMITED` với HTTP
429 khi vượt ngưỡng cấu hình.

| Method | Path | Mục đích |
|---|---|---|
| POST | `/chat/sessions` | Tạo anonymous/authenticated session |
| GET | `/chat/sessions/{session_id}/messages` | Lịch sử phiên, kiểm tra quyền bằng session token |
| POST | `/chat/sessions/{session_id}/messages` | Gửi câu hỏi và nhận câu trả lời RAG |
| POST | `/chat/sessions/{session_id}/support-tickets` | Tạo yêu cầu chuyển nhân viên |

Request message: `message`, `client_message_id`. Response:

```json
{
  "data": {
    "message_id": "uuid",
    "answer": "...",
    "product_cards": [{"name": "...", "image_url": "...", "effective_price": 249000, "url": "/san-pham/..."}],
    "sources": [{"type": "faq", "title": "..."}],
    "grounding_status": "grounded",
    "context": {"session_id": "uuid"}
  }
}
```

`grounding_status`: `grounded`, `insufficient_data`, `out_of_scope`, `provider_unavailable`. Product card luôn được tạo từ dữ liệu SQL đã hydrate, không parse từ prose của model. Session anonymous dùng token ngẫu nhiên riêng, không cho đoán ID để đọc transcript.

## 6. Admin

Tất cả endpoint dưới `/admin` yêu cầu role `admin`.

- `GET /admin/auth-check`: endpoint nền tảng BE-04 để xác minh session có role admin; trả user hiện tại theo success envelope và không trả `password_hash`.

### Dashboard

- `GET /admin/dashboard`: counts product/customer/order và demo revenue theo định nghĩa đã công bố.

### Catalog và variant

- CRUD `/admin/categories`
- CRUD `/admin/products`
- CRUD `/admin/products/{product_id}/images`
- CRUD `/admin/products/{product_id}/variants`
- `PATCH /admin/variants/{variant_id}/stock`
- CRUD `/admin/colors`, `/admin/sizes`, `/admin/labels`

Mutation product/knowledge trả `index_status` (`pending`, `indexed`, `failed`) khi liên quan embedding. Xóa product mặc định soft-delete nếu đã xuất hiện trong order.

### Order và customer

- `GET /admin/orders`, `GET /admin/orders/{id}`
- `PATCH /admin/orders/{id}/status` với state transition hợp lệ
- `GET /admin/customers`, `GET /admin/customers/{id}` và `/orders`

Customer response không có `password_hash` hoặc reset token.

### Coupon

- CRUD `/admin/coupons`; validate code, kiểu discount, giá trị/maximum, minimum subtotal, thời gian, usage limit và active state.

### RAG content và indexing

- CRUD `/admin/knowledge-documents` cho `faq`, `size_guide`, `shipping_policy`, `return_policy`, `promotion`, `guide`.
- `POST /admin/knowledge-documents/{id}/reindex`
- `GET /admin/rag-index-jobs` và `GET /admin/rag-index-jobs/{id}`

### Support

- `GET /admin/support-tickets`
- `GET /admin/support-tickets/{id}` gồm transcript
- `PATCH /admin/support-tickets/{id}` cập nhật trạng thái/ghi chú nội bộ

## 7. Upload và media

- `POST /admin/media/images` dùng multipart, kiểm tra MIME thực, kích thước, extension allow-list và tạo tên file an toàn.
- Response trả URL tương đối/public; frontend không suy ra filesystem path.
- Xóa ảnh phải kiểm tra ảnh đang được tham chiếu; ảnh placeholder/seed là local.

## 8. State machine bắt buộc

Order transitions:

```text
Chờ xác nhận -> Đã xác nhận -> Đang chuẩn bị -> Đang giao -> Hoàn thành
      └-------------> Đã hủy
Đã xác nhận --------> Đã hủy
```

Không hủy từ `Đang chuẩn bị` trở đi. Backend là nơi duy nhất enforce transition. Support ticket tối thiểu: `open -> in_progress -> resolved`, có thể `closed` theo quyết định triển khai.

## 9. Contract verification

- Backend snapshot/export OpenAPI.
- Frontend/RAG generated types hoặc contract fixtures từ OpenAPI.
- QA test status code, error code, auth boundary, pagination và state transition.
- Thay đổi breaking phải cập nhật file này và consumer trước khi merge.
