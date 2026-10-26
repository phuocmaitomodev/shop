# Kiến trúc tổng thể

> **Phạm vi MVP hiện hành:** Theo quyết định thu gọn ngày 2026-10-26, implementation/release gate chỉ gồm catalog công khai, product detail tối giản và chat RAG sản phẩm. Xem [`mvp-product-rag-scope.md`](mvp-product-rag-scope.md). Các phần auth, commerce, admin và support dưới đây được giữ làm kiến trúc mục tiêu lịch sử, không thuộc MVP hiện tại.

## 1. Mục tiêu và phạm vi

Hệ thống là website demo bán quần áo tiếng Việt gồm storefront, trang quản trị và chatbot RAG. Hệ thống chạy local bằng Docker Compose, dùng Vue 3 + Vite, FastAPI, PostgreSQL + pgvector và Gemini API. Kiến trúc ưu tiên rõ ràng, dễ dựng lại và đủ để nghiệm thu; không thiết kế các năng lực production nằm ngoài `request.md`.

## 2. Kiến trúc logic

```text
Trình duyệt (desktop/mobile)
  └─ Vue 3 SPA
      ├─ Storefront + tài khoản + cart/checkout
      ├─ Admin console
      └─ Chat widget
           │ HTTPS/JSON (local: HTTP)
           ▼
FastAPI modular monolith
  ├─ Auth & RBAC
  ├─ Catalog/Search
  ├─ Cart/Pricing/Coupon
  ├─ Checkout/Order/Inventory
  ├─ Admin/Content/Support
  └─ Chat/RAG orchestration
       ├─ SQL structured retrieval ───────┐
       ├─ Vector retrieval               │
       └─ Gemini generation              │
                                         ▼
                              PostgreSQL + pgvector
                              ├─ transactional tables
                              ├─ chat/support history
                              └─ documents/chunks/vectors

Local filesystem: ảnh demo sản phẩm
External dependency duy nhất: Gemini API
```

## 3. Quyết định kiến trúc

### 3.1. Modular monolith

Backend được triển khai như một FastAPI service có module nghiệp vụ rõ ràng thay vì microservices. Điều này giảm độ phức tạp Docker/network/transaction cho bản demo nhưng vẫn giữ boundary để các profile làm việc độc lập. Module không truy cập bảng của nhau tùy tiện; trao đổi qua service/repository interface nội bộ.

### 3.2. SPA theo route và vai trò

Một Vue SPA có hai vùng route:

- Storefront: public catalog, product detail, cart, checkout, account và widget chat.
- Admin: route được bảo vệ bằng role `admin`, cung cấp dashboard và CRUD.

Frontend không giữ secret, không gọi Gemini hoặc PostgreSQL trực tiếp. Trạng thái server được quản lý tách với trạng thái UI/cart tạm thời. Guest nhận `guest_session_id` không chứa PII để gắn cart/chat.

### 3.3. PostgreSQL là nguồn dữ liệu chuẩn

PostgreSQL là source of truth cho user, catalog, variant, stock, coupon, order, chat và support ticket. pgvector chỉ phục vụ semantic retrieval. Giá, sale price, coupon, size, màu và tồn kho không được tin từ embedding; phải truy vấn/hydrate từ SQL khi trả lời hoặc checkout.

### 3.4. Nhất quán tồn kho và đơn hàng

Checkout chạy trong transaction:

1. Validate cart và coupon.
2. Lock các variant liên quan (`SELECT ... FOR UPDATE`).
3. Đọc lại giá và stock hiện tại.
4. Từ chối nếu giá/stock không còn hợp lệ theo policy API.
5. Tạo order + order items snapshot và trừ tồn kho.
6. Commit; trả order code.

Order item lưu snapshot tên/SKU/màu/size/giá để lịch sử không thay đổi khi catalog được sửa. Hủy đơn hợp lệ phải hoàn tồn kho một lần trong cùng transaction.

### 3.5. Đồng bộ embedding

Thay đổi product hoặc knowledge document tạo trạng thái reindex bền vững trong database. Worker nền trong cùng backend process (hoặc command chạy riêng trong Compose) claim job, tạo embedding và đánh dấu thành công/thất bại. API cập nhật nghiệp vụ không phụ thuộc Gemini để commit dữ liệu; UI admin hiển thị trạng thái index. Cơ chế phải idempotent và retry được.

## 4. Thành phần triển khai dự kiến

| Thành phần | Công nghệ | Trách nhiệm |
|---|---|---|
| `web` | Vue 3, Vite | Storefront, admin UI, chat widget |
| `api` | Python, FastAPI | REST API, auth, business rules, RAG orchestration |
| `rag-worker` | Cùng codebase Python | Chunk/embed/reindex bất đồng bộ |
| `db` | PostgreSQL + pgvector | Transactional data và vector index |
| `media` | Docker volume/bind mount | Ảnh demo local |

Docker Compose phải có healthcheck và dependency readiness; migration và seed là command rõ ràng, không chạy seed ngầm mỗi lần start.

## 5. Module backend dự kiến

- `auth`: register/login/logout/refresh/forgot-password giả lập an toàn, RBAC.
- `catalog`: category, product, image, labels, variants, search/filter/sort/related.
- `cart`: guest/authenticated cart và kiểm tra variant.
- `pricing`: VND, sale price, coupon, shipping fee/free threshold.
- `orders`: checkout, snapshot, state machine, cancellation, history.
- `admin`: dashboard và các use case quản trị.
- `content`: FAQ, size guide, shipping/return/promotion documents.
- `chat`: session/message persistence, retrieval, generation, product cards.
- `support`: ticket và transcript.
- `rag`: indexing, SQL retrieval, vector retrieval, guardrails.

## 6. Authentication và authorization

- Email/password; password chỉ lưu hash mạnh.
- Hai role duy nhất: `customer`, `admin`.
- Access/refresh token nên vận chuyển bằng cookie `HttpOnly`, `SameSite=Lax`; mutation dùng kiểm soát CSRF phù hợp với cách deploy.
- Public: catalog, guest cart/checkout và chat.
- Customer: profile, order history/detail/cancel của chính họ.
- Admin: dashboard và CRUD; tuyệt đối không trả password hash qua API.
- Forgot password trong demo tạo token có hạn; không gửi email thật. Response không tiết lộ email có tồn tại hay không; README nêu cách lấy link/token demo an toàn ở local.

## 7. Luồng chính

### Duyệt và tìm sản phẩm

Browser gọi catalog API với filter/sort/pagination. Backend dùng index SQL, chỉ trả variant availability tổng hợp cần thiết. Product detail trả images, labels, variants và sản phẩm liên quan.

### Checkout

Frontend gửi cart/version, thông tin nhận hàng, coupon và payment method. Backend tính lại toàn bộ subtotal/discount/shipping/total; giá frontend chỉ để hiển thị. COD hoàn chỉnh; online trả trạng thái mô phỏng được ghi rõ.

### Chat RAG

Frontend gửi `session_id` + message. Backend phân loại ý định, dùng SQL cho product constraints và vector cho nội dung tự nhiên, hydrate dữ liệu động, dựng context có cấu trúc, gọi Gemini và validate output. Message, source và product cards được lưu/return. Thiếu nguồn thì trả fallback, không suy đoán.

### Support handoff

Từ chat session, backend tạo ticket idempotent có mã công khai; admin đọc ticket cùng transcript. Không tạo kết nối live agent.

## 8. Cấu hình

Biến môi trường tối thiểu dự kiến:

- `DATABASE_URL`
- `APP_SECRET_KEY`, `ACCESS_TOKEN_TTL_MINUTES`, `REFRESH_TOKEN_TTL_DAYS`
- `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_EMBEDDING_MODEL`, `EMBEDDING_DIMENSION`
- `SHIPPING_FLAT_FEE`, `FREE_SHIPPING_THRESHOLD`
- `MEDIA_ROOT`, `PUBLIC_MEDIA_BASE_URL`
- `CORS_ALLOWED_ORIGINS`, `APP_ENV`

`.env.example` chỉ chứa placeholder. Startup phải fail-fast khi cấu hình bắt buộc thiếu, trừ command/test không cần Gemini.

## 9. Quan sát và xử lý lỗi trong phạm vi local

- Structured logs kèm request ID; không log secret/password/token.
- Error envelope thống nhất theo `api-contract.md`.
- Health endpoints tách liveness/readiness; readiness kiểm tra database, không bắt buộc Gemini hoạt động.
- Gemini timeout/retry hữu hạn; khi unavailable chatbot trả lỗi/fallback rõ ràng, không ảnh hưởng luồng bán hàng.

## 10. Yêu cầu phi chức năng

- Mobile-first, touch target phù hợp và không overflow/chồng lấn.
- Pagination cho danh sách public/admin; tránh N+1 query.
- Các endpoint thay đổi tồn kho/order có transaction và idempotency phù hợp.
- Internal links hợp lệ; các trang chính trả HTTP thành công.
- Seed xác định được và tạo đúng 100 sản phẩm.
- Backup, HA, CDN, autoscaling, monitoring production và compliance pháp lý nằm ngoài phạm vi demo.
