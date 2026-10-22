# Database schema dự kiến

## 1. Quy ước

- PostgreSQL + extension `vector`; UUID làm primary key, `timestamptz` lưu UTC.
- Tiền VND dùng `bigint` và constraint `>= 0`; không dùng float.
- Bảng nghiệp vụ có `created_at`, `updated_at`; bảng cần audit có `created_by`/`updated_by`.
- Email chuẩn hóa lowercase và unique; password chỉ lưu hash.
- Enum có thể dùng PostgreSQL enum hoặc `text + CHECK`; migration phải quản lý rõ.
- Soft delete (`deleted_at`/`is_active`) cho product/content đã được tham chiếu; order history không cascade mất dữ liệu.
- Mọi foreign key và unique/check/index nêu dưới đây là contract tối thiểu.

## 2. Identity và auth

### `users`

- `id`, `email` unique, `password_hash`, `full_name`, `phone` nullable.
- `role`: `customer | admin`; `is_active`; timestamps.
- Không bao giờ expose `password_hash` qua API.

### `auth_sessions`

- `id`, `user_id`, `refresh_token_hash`, `expires_at`, `revoked_at`, metadata tối thiểu.
- Index `(user_id, expires_at)`; chỉ lưu hash token.

### `password_reset_tokens`

- `id`, `user_id`, `token_hash`, `expires_at`, `used_at`, `created_at`.
- Token dùng một lần; index/unique trên `token_hash`.

## 3. Catalog

### `categories`

- `id`, `name`, `slug` unique, `description`, `sort_order`, `is_active`.
- Seed tối thiểu các nhóm trong yêu cầu.

### `products`

- `id`, `category_id`, `sku` unique, `slug` unique, `name`, `description`.
- `price`, `sale_price` nullable; check `sale_price > 0 AND sale_price < price` khi có.
- `is_active`, `published_at`, `deleted_at`, timestamps.

### `product_images`

- `id`, `product_id`, `file_path`, `alt_text`, `sort_order`, `is_primary`.
- Unique partial index bảo đảm tối đa một ảnh primary/product.
- Chỉ lưu path/URL tương đối, không lưu binary trong DB.

### `colors`

- `id`, `name`, `slug` unique, `hex_code` nullable, `is_active`.

### `sizes`

- `id`, `code` unique (`S`, `M`, `L`, `XL`, `XXL`), `name`, `sort_order`, `is_active`.

### `product_variants`

- `id`, `product_id`, `color_id`, `size_id`, `variant_sku` unique.
- `stock_quantity >= 0`, `is_active`, `version` cho optimistic response/cache.
- Unique `(product_id, color_id, size_id)`.
- Index `(product_id, is_active)`, `(color_id, size_id, stock_quantity)` phục vụ filter.

### `labels`, `product_labels`

- `labels`: `id`, `code` unique (`new`, `best_seller`, `sale`), `display_name`.
- Join table unique `(product_id, label_id)`.

Đúng 100 products được bảo đảm bởi seed verification, không phải database constraint toàn cục. Mỗi product seed phải có 2–4 màu và variant theo size/tồn kho hợp lệ.

## 4. Cart và pricing

### `carts`

- `id`, `user_id` nullable, `guest_token_hash` nullable, `status` (`active|converted|abandoned`), `version`, timestamps.
- Check cart có đúng một owner mode hợp lệ; index cart active theo user/guest.

### `cart_items`

- `id`, `cart_id`, `variant_id`, `quantity > 0`, timestamps.
- Unique `(cart_id, variant_id)`.
- Giá hiển thị được tính hiện hành; cart item không là nguồn giá cuối checkout.

### `coupons`

- `id`, `code` case-insensitive unique, `description`, `discount_type` (`fixed|percent`).
- `discount_value > 0`, `max_discount` nullable, `min_subtotal >= 0`.
- `starts_at`, `ends_at`, `usage_limit`, `per_user_limit`, `used_count`, `is_active`.
- Checks phần trăm trong phạm vi hợp lệ và thời gian hợp lệ.

### `coupon_redemptions`

- `id`, `coupon_id`, `order_id`, `user_id` nullable, `guest_fingerprint` nullable, `discount_amount`, `created_at`.
- Unique `(coupon_id, order_id)`; cập nhật usage trong transaction checkout.

### `system_settings`

- `key` primary key, `value_json`, timestamps.
- Chỉ dùng allow-list cho `shipping_flat_fee`, `free_shipping_threshold`; service validate type/range.

## 5. Orders và inventory

### `orders`

- `id`, `order_code` unique, `user_id` nullable, `cart_id` nullable.
- Recipient snapshot: `recipient_name`, `phone`, `address_line`, `ward`, `district`, `province`, `note`.
- `status`: `pending_confirmation`, `confirmed`, `preparing`, `shipping`, `completed`, `cancelled`.
- `payment_method`: `cod|online_demo`; `payment_status`: `pending|demo_approved|demo_declined|paid|cancelled` theo phạm vi demo.
- Totals: `subtotal`, `discount_amount`, `shipping_fee`, `total` với checks không âm và công thức được service enforce/test.
- `coupon_id` nullable, `guest_lookup_token_hash` nullable, timestamps/cancel metadata.
- Index `(user_id, created_at desc)`, `(status, created_at desc)`.

### `order_items`

- `id`, `order_id`, `product_id` nullable, `variant_id` nullable.
- Snapshot: `product_name`, `product_sku`, `variant_sku`, `color_name`, `size_code`, `image_url`.
- `unit_price`, `quantity > 0`, `line_total`.
- FK product/variant dùng `ON DELETE SET NULL`; snapshot giữ lịch sử.

### `inventory_movements`

- `id`, `variant_id`, `order_id` nullable, `type` (`seed|admin_adjustment|order_reserve|order_cancel_restore`).
- `quantity_delta` khác 0, `stock_after >= 0`, `reason`, `created_by` nullable, `created_at`.
- Idempotency/unique reference phù hợp để không trừ/hoàn hai lần cho cùng order transition.

State transition do service enforce trong transaction; database constraint bảo vệ enum/check, audit movement chứng minh thay đổi stock.

## 6. Nội dung RAG và vector

### `knowledge_documents`

- `id`, `document_type`: `faq|size_guide|shipping_policy|return_policy|promotion|guide`.
- `title`, `content`, `locale` mặc định `vi`, `is_active`, `version`, `checksum`, timestamps.

### `rag_documents`

Lớp chuẩn hóa cho mọi source có embedding:

- `id`, `source_type` (`product|knowledge`), `source_id`, `title`, `content_for_embedding`.
- `source_version`, `checksum`, `index_status` (`pending|indexed|failed`), `is_active`, timestamps.
- Unique `(source_type, source_id)`.

### `rag_chunks`

- `id`, `rag_document_id`, `chunk_index`, `content`, `metadata jsonb`.
- `embedding vector(EMBEDDING_DIMENSION)`, `embedding_model`, `source_version`, `is_active`, timestamps.
- Unique `(rag_document_id, source_version, chunk_index)`.
- Vector index HNSW/IVFFlat tùy dataset; thêm FTS GIN index cho hybrid keyword.

`EMBEDDING_DIMENSION` phải được chốt trước migration và khớp model; thay model khác dimension cần migration/reindex rõ ràng, không âm thầm trộn vectors.

### `rag_index_jobs`

- `id`, `source_type`, `source_id`, `source_version`, `status` (`pending|processing|succeeded|failed`).
- `attempt_count`, `available_at`, `locked_at`, `last_error`, timestamps.
- Unique idempotency `(source_type, source_id, source_version)`.

## 7. Chat và support

### `chat_sessions`

- `id`, `user_id` nullable, `anonymous_token_hash` nullable, `status`, `context_state jsonb`, `last_message_at`, timestamps.
- Anonymous access được xác minh bằng token hash, không chỉ session UUID.

### `chat_messages`

- `id`, `session_id`, `role` (`user|assistant|system_event`), `content`.
- `client_message_id` nullable để idempotency, `grounding_status`, `model_name` nullable, `created_at`.
- Unique partial `(session_id, client_message_id)` khi có.

### `chat_message_sources`

- `id`, `message_id`, `source_type`, `source_id`, `chunk_id` nullable, `product_id` nullable.
- `rank`, `score` nullable, `source_version`; index theo message.

### `support_tickets`

- `id`, `ticket_code` unique, `chat_session_id`, `customer_id` nullable.
- `status` (`open|in_progress|resolved|closed`), `subject`, `admin_note`, `assigned_admin_id` nullable, timestamps.
- Có unique/idempotency rule để retry cùng request không tạo nhiều ticket ngoài ý muốn.

## 8. Admin/audit tùy chọn nhưng khuyến nghị

### `audit_logs`

- `id`, `actor_user_id`, `action`, `entity_type`, `entity_id`, `before_json`, `after_json`, `request_id`, `created_at`.
- Không lưu password hash/token/secret trong before/after.

## 9. Quan hệ chính

```text
categories 1─N products 1─N product_variants N─1 colors/sizes
products 1─N product_images; products N─N labels
users/guest 1─N carts 1─N cart_items N─1 product_variants
users/guest 1─N orders 1─N order_items
orders N─0..1 coupons; product_variants 1─N inventory_movements
knowledge_documents/products 1─1 rag_documents 1─N rag_chunks
users/anonymous 1─N chat_sessions 1─N chat_messages 1─N sources
chat_sessions 1─N support_tickets
```

## 10. Migration và seed verification

Migration order dự kiến: extensions/enums → identity → catalog → cart/pricing → orders/inventory → knowledge/vector → chat/support → indexes.

Seed phải:

- Tạo đúng 100 products tiếng Việt trong 7 nhóm yêu cầu.
- Tạo variants với S/M/L/XL và một số XXL, mỗi product 2–4 màu, stock không âm.
- Tạo labels, local image references, FAQ, size guide, policies, promotions.
- Tạo admin demo và một số customer bằng password từ config/seed output an toàn.
- Có verification query/test đếm product, kiểm tra SKU/slug/variant uniqueness và orphan rows.
- Chạy idempotent hoặc fail rõ ràng; README nêu cách reset database demo.
