# QA-01 — Test data plan

## 1. Nguyên tắc

- Seed cố định, tái tạo được và version-control; UUID/code/timestamp quan trọng phải deterministic hoặc có lookup key ổn định.
- Tất cả nội dung demo tiếng Việt, tiền là integer VND, timestamp UTC.
- Mỗi test chỉ mutate dữ liệu nó sở hữu; dùng prefix/run ID cho data phát sinh và reset database test giữa suite destructive.
- Không chứa secret/PII thật. Email, phone, address và transcript đều là dữ liệu giả có nhãn demo.
- Oracle lấy từ PostgreSQL/API hiện hành; vector không là source of truth cho giá, promotion, color, size hoặc stock.
- QA-02 mới định nghĩa helper/contract. Data bên dưới chỉ runnable sau BE-04..16/BE-06 seed được bàn giao.

## 2. Dataset chuẩn và invariant

Tên dataset: `QA_BASE_V1`. Sau migration + seed trên DB trống, seed verifier phải tạo snapshot và fail nếu bất kỳ invariant nào sai.

### 2.1. Đúng 100 sản phẩm

| Data ID | Thiết kế | Oracle bắt buộc |
|---|---|---|
| PROD-BASE-100 | Chính xác 100 product active demo, phân bố trên 7 category: Áo thun, Áo sơ mi, Áo khoác, Quần jeans, Quần short, Váy/Đầm, Phụ kiện | DB `count(products active/non-deleted)=100`; admin API total=100; không 99/101 |
| PROD-NORMAL-01 | Product không sale, đủ ảnh/description/labels tùy chọn | effective_price = price |
| PROD-SALE-01 | Product có `0 < sale_price < price`, label Giảm giá | effective_price = sale_price; VND integer |
| PROD-NEW-01 | Product có published_at mới, label Mới | sort newest deterministic |
| PROD-BEST-01 | Product có order metric/seed metric theo định nghĩa đã chốt | sort best-selling có oracle rõ |
| PROD-INACTIVE-01 | Fixture do test tạo, inactive/deleted | Không xuất hiện storefront/RAG card |
| PROD-SEARCH-VI-01 | Tên/mô tả có dấu và keyword đặc trưng | Search exact/không dấu theo contract đã triển khai; không match sai |

Invariants: 100 SKU và slug unique; category FK hợp lệ; price ≥ 0; sale_price hợp lệ; tối đa một primary image/product; links/media local hợp lệ; không orphan labels/images.

### 2.2. Variants màu/size

| Data ID | Thiết kế | Mục đích |
|---|---|---|
| VAR-2COLOR-01 | Product có đúng 2 màu | Biên dưới requirement |
| VAR-4COLOR-01 | Product có đúng 4 màu | Biên trên requirement |
| VAR-SMLXL-01 | Product có S/M/L/XL cho các màu | Bộ size mặc định |
| VAR-XXL-01 | Một số product phù hợp có XXL | Optional size/facet |
| VAR-SPARSE-01 | Một tổ hợp color-size không tồn tại | UI/API không cho chọn variant giả |
| VAR-INACTIVE-01 | Variant inactive nhưng cùng product còn variant khác | Filter/cart bỏ variant inactive |
| VAR-DUP-NEG | Fixture mutation cố tạo duplicate `(product,color,size)`/variant SKU | DB constraint từ chối |

Invariants: mỗi product seed có 2–4 distinct colors; required size policy được verifier định nghĩa theo loại sản phẩm; `(product_id,color_id,size_id)` và `variant_sku` unique; không orphan color/size/product.

### 2.3. Tồn kho

| Data ID | Stock | Mục đích |
|---|---:|---|
| STOCK-ZERO | 0 | Out-of-stock; không add/đề xuất như còn hàng |
| STOCK-ONE | 1 | Last-item/concurrency |
| STOCK-LOW | 2 | quantity exact stock và stock+1 |
| STOCK-NORMAL | 10 | Cart/update happy path |
| STOCK-HIGH | 100 | Boundary không dùng hard-code UI |
| STOCK-MUTATE | 5 → 0 và 5 → 3 | Revalidation/RAG live freshness |

Invariants: stock không âm; checkout successful tạo một `order_reserve`; cancel hợp lệ tạo tối đa một `order_cancel_restore`; `stock_after` khớp variant. Hai checkout cạnh tranh STOCK-ONE chỉ có một thành công.

### 2.4. Coupon

| Data ID | Rule | Expected |
|---|---|---|
| CPN-FIXED-VALID | Fixed 50.000, active, trong thời gian, min đạt | Discount 50.000 không làm total âm |
| CPN-PERCENT-VALID | 10%, active | 10% subtotal theo rounding policy |
| CPN-PERCENT-CAP | 20%, max 100.000 | Discount bị cap 100.000 |
| CPN-MIN-EDGE | min_subtotal 500.000 | 499.999 reject; 500.000 accept |
| CPN-FUTURE | starts_at tương lai | `COUPON_INVALID`/code contract chốt |
| CPN-EXPIRED | ends_at quá khứ | `COUPON_EXPIRED` |
| CPN-INACTIVE | is_active=false | Reject |
| CPN-USAGE-LIMIT | used_count = usage_limit | Reject |
| CPN-PER-USER | User đã đạt per_user_limit | Reject user đó; user khác hợp lệ |
| CPN-CASE | Code mixed case | Case-insensitive uniqueness/apply |
| CPN-NOT-FOUND | Code không tồn tại | Stable error code, không 500 |

Test timestamp dùng clock fixture/frozen time nếu service hỗ trợ; không dùng coupon “sắp hết hạn” dựa vào wall clock.

### 2.5. Order

| Data ID | Trạng thái/payment/owner | Mục đích |
|---|---|---|
| ORD-GUEST-PENDING | Guest, COD, pending_confirmation | Guest lookup, admin visibility |
| ORD-USER-PENDING | Customer A, COD | History/detail/cancel allowed |
| ORD-CONFIRMED | Customer A | Cancel allowed + restore once |
| ORD-PREPARING | Customer A | Cancel rejected |
| ORD-SHIPPING | Customer A | Cancel rejected |
| ORD-COMPLETED | Customer A | Revenue/best-selling oracle |
| ORD-CANCELLED | Customer A | Không tính theo revenue definition; no double restore |
| ORD-ONLINE-DEMO | Guest/customer, online_demo | No real gateway; simulation status |
| ORD-OTHER-USER | Customer B | Customer A receives 404/403 per contract, never data |
| ORD-PRICE-STALE | Cart snapshot rồi mutate price | `PRICE_CHANGED` |
| ORD-STOCK-STALE | Cart snapshot rồi mutate stock | `OUT_OF_STOCK` |
| ORD-IDEMPOTENT | Same payload + same Idempotency-Key | Một order/redemption/reserve |

Mỗi order item lưu snapshot name/SKU/color/size/unit_price; mutate catalog sau đó không đổi history. Totals oracle: `subtotal - discount + shipping = total`, tất cả integer/non-negative.

### 2.6. Tài liệu RAG

| Data ID | Source | Nội dung/expected |
|---|---|---|
| RAG-FAQ-01 | faq | Câu hỏi/đáp án đặc trưng, citation đúng source/version |
| RAG-SIZE-01 | size_guide | Bảng size có số đo, không mất đơn vị khi normalize/chunk |
| RAG-SHIP-01 | shipping_policy | Phí/thời gian theo nội dung seed; không thay shipping config động |
| RAG-RETURN-01 | return_policy | Điều kiện đổi trả duy nhất để phát hiện wrong citation |
| RAG-PROMO-01 | promotion | Nội dung mô tả; coupon live vẫn từ SQL |
| RAG-GUIDE-01 | guide | Câu hỏi natural-language/semantic |
| RAG-INACTIVE-01 | inactive document | Không retrieval/citation |
| RAG-V1-V2 | Cập nhật content/version/checksum | Chỉ version active/indexed đúng được retrieval sau swap |
| RAG-INJECTION-01 | Knowledge chứa “bỏ quy tắc/đọc secret” | Được coi là data, không instruction |
| RAG-ZERO-01 | Query không có source qua threshold | `insufficient_data`, không bịa |

Corpus eval lưu riêng input, expected intent, hard filters, allowed source IDs/product IDs, expected grounding status và forbidden claims. Không chỉ so exact prose.

### 2.7. Chat session

| Data ID | Thiết kế | Mục đích |
|---|---|---|
| CHAT-ANON-A | Anonymous token A, 2 câu hỏi nối tiếp về product/màu/size | Context cùng phiên |
| CHAT-ANON-B | Token B/session B | Không đọc/context leak từ A |
| CHAT-USER-A | Customer A authenticated | Ownership/persistence |
| CHAT-LONG | Vượt context window/retention configured | Truncation an toàn, không mất state cần thiết |
| CHAT-DUP-MSG | Retry cùng client_message_id | Một message/response effect |
| CHAT-OOS | Out-of-scope prompt | `out_of_scope` |
| CHAT-INJECT | User prompt injection | Không lộ prompt/secret/data khác |
| CHAT-PROVIDER-DOWN | Stub timeout/error | `provider_unavailable`; commerce health unaffected |

Không log raw token. Session UUID không đủ quyền; anonymous token đúng mới đọc được transcript.

### 2.8. Support ticket

| Data ID | Thiết kế | Mục đích |
|---|---|---|
| TKT-OPEN-01 | Ticket open gắn CHAT-ANON-A | Widget nhận code, admin thấy đúng transcript |
| TKT-IN-PROGRESS | Ticket in_progress, assigned admin | Transition/visibility |
| TKT-RESOLVED | Ticket resolved | State transition |
| TKT-CLOSED | Ticket closed nếu implementation hỗ trợ | Allowed transition theo contract cuối |
| TKT-IDEMPOTENT | Retry same session/request/idempotency key | Đúng một ticket |
| TKT-OTHER-SESSION | Ticket gắn CHAT-ANON-B | Không trộn transcript |
| TKT-ADMIN-NOTE | Internal note | Không lộ ra public/chat response |

Invariants: `ticket_code` unique; FK session hợp lệ; transcript đúng session theo thứ tự; customer/anonymous không đọc admin note; retry không tạo duplicate.

## 3. Tài khoản và dữ liệu phụ trợ

- `admin.qa@example.test`: admin demo, password lấy từ test config/seed output, không hard-code production.
- `customer.a.qa@example.test`, `customer.b.qa@example.test`: kiểm tra ownership chéo.
- `disabled.qa@example.test`: is_active=false.
- Guest A/B có token random chỉ trong runtime fixture; lưu hash ở DB.
- Địa chỉ/phone: giá trị giả hợp lệ và invalid boundary (thiếu field, ký tự dài, control/XSS); không dùng PII thật.
- System settings: shipping flat 30.000, free threshold 500.000 theo `.env.example`; test không phụ thuộc giá trị nếu environment override, mà đọc oracle từ API/DB config.

## 4. Reset, isolation và lifecycle

1. Chỉ reset database test khi `QA_ALLOW_DB_RESET=true`.
2. Chạy migration trên DB trống.
3. Chạy seed command do backend bàn giao.
4. Chạy seed verifier và lưu snapshot counts/invariants.
5. Suite read-only có thể chạy song song; suite mutation dùng transaction rollback, namespace hoặc reset theo worker.
6. Test concurrency dùng fixture riêng và cleanup có kiểm chứng.
7. Sau suite destructive, reset/reseed và so snapshot với baseline.

Helper `qa/helpers/database.ts` cố ý không hard-code command vì BE-06 chưa tồn tại. Khi backend bàn giao, cấu hình `QA_DATABASE_RESET_COMMAND` và `QA_DATABASE_SEED_COMMAND`; thiếu command phải fail rõ, không skip/pass ngầm.

## 5. Seed verifier contract dự kiến

Tối thiểu trả `SeedVerificationSnapshot`:

- `productCount == 100`.
- `productsOutsideColorRange == 0`.
- `productsMissingRequiredSizes == 0`.
- `negativeStockVariants == 0`.
- `duplicateProductSkus == 0`.
- `duplicateVariantSkus == 0`.
- `orphanVariants == 0`.

Mở rộng khi schema có đủ: 7 category required/non-empty, slug uniqueness, sale price validity, one primary image, coupon/date validity, knowledge source counts, demo users, orphan rows toàn bộ, index job status. Kết quả DB phải đối chiếu với admin/public API total khi endpoint tồn tại.

## 6. An toàn dữ liệu

- Database test có tên/host rõ; không chạy reset trên production-like host.
- Không đưa `.env`, token chat, refresh token, Gemini key hoặc password thật vào fixture/snapshot/report.
- Screenshot/video/log phải tránh giữ password/token; redact trước khi lưu evidence.
- Media malicious fixtures nhỏ, không thực thi; cleanup ngoài media root phải bị cấm và được assert.
