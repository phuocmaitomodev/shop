# Thiết kế RAG: hybrid retrieval SQL + pgvector

## 1. Mục tiêu

Chatbot trả lời tiếng Việt về sản phẩm, size, giao hàng, đổi trả, khuyến mãi và FAQ; đề xuất product card có link; nhớ ngữ cảnh trong một session; không bịa giá, tồn kho, chính sách hoặc sản phẩm. PostgreSQL là nguồn sự thật, pgvector hỗ trợ hiểu ngôn ngữ tự nhiên, Gemini chỉ tổng hợp từ context được cấp.

## 2. Phân loại nguồn dữ liệu

### Dữ liệu có cấu trúc — luôn truy vấn SQL

- Product/category/label.
- Giá, sale price và hiệu lực khuyến mãi.
- Color, size, variant, stock.
- Coupon và điều kiện áp dụng.
- Link/ảnh product hiện hành.

### Dữ liệu văn bản — vector retrieval

- FAQ.
- Size guide.
- Shipping/return policy.
- Promotion/guide content.
- Phần mô tả/thuộc tính ngữ nghĩa của sản phẩm để tăng khả năng tìm theo nhu cầu.

Embedding sản phẩm không chứa giá/tồn kho như nguồn trả lời. ID product từ vector chỉ là candidate; toàn bộ trường hiển thị phải hydrate lại bằng SQL.

## 3. Pipeline indexing

1. Admin/seed tạo hoặc cập nhật source entity.
2. Transaction ghi `rag_documents` và tạo `rag_index_jobs` trạng thái `pending` (outbox/job bền vững).
3. Worker claim job bằng lock có `SKIP LOCKED`.
4. Normalize tiếng Việt có kiểm soát, giữ tiêu đề và metadata; không làm mất số đo/đơn vị.
5. Chunk theo heading/đoạn, có overlap nhỏ; mỗi chunk giữ `document_id`, `source_type`, `source_id`, version/checksum.
6. Gọi embedding model cấu hình bởi `GEMINI_EMBEDDING_MODEL`; dimension khớp migration/config.
7. Upsert chunks + vectors atomically cho version mới, xóa/deactivate version cũ, đánh dấu `indexed`.
8. Retry hữu hạn với backoff; lưu error đã sanitize khi `failed`.

Job idempotent theo `(source_type, source_id, source_version)`. Xóa/disable source phải loại khỏi retrieval. Không giữ embedding mồ côi.

## 4. Pipeline truy vấn hybrid

### Bước A — kiểm tra và chuẩn hóa input

- Giới hạn độ dài, loại control characters, rate limit theo session/IP ở mức hợp lý.
- Lưu message user; không xem text người dùng là system instruction.
- Lấy một cửa sổ hội thoại gần nhất và state tóm tắt có cấu trúc (intent/filters/product refs), không nhồi toàn bộ transcript không giới hạn.

### Bước B — phân loại ý định và trích filter

Bộ phân loại trả schema allow-list, ví dụ:

- `product_search`: category, min/max price, colors, sizes, keywords.
- `product_fact`: product/SKU + field cần hỏi.
- `knowledge_question`: source types phù hợp.
- `support_handoff`.
- `out_of_scope`.

Giá trị filter được validate bằng code; không ghép SQL từ text. Nếu entity mơ hồ, chatbot hỏi lại hoặc tìm candidate, không tự chọn bừa.

### Bước C — retrieval

- Product intent: SQL filters là bắt buộc; full-text/trigram có thể hỗ trợ keyword. Vector product-description chỉ bổ sung/rerank candidates.
- Knowledge intent: vector top-k với filter `source_type`, `active`, locale; có thể kết hợp keyword PostgreSQL FTS.
- Query hỗn hợp: chạy SQL và vector song song, hợp nhất theo entity/source ID. Có thể dùng Reciprocal Rank Fusion hoặc trọng số đã test; không cộng trực tiếp score khác thang đo.
- Áp similarity threshold và giới hạn top-k/context token. Không có candidate qua ngưỡng thì `insufficient_data`.

### Bước D — SQL hydration

Ngay trước generation, batch query lại product IDs để lấy giá, sale price, variant, size/màu còn hàng, ảnh và URL hiện tại. Loại product inactive/deleted/hết điều kiện. Context gắn `retrieved_at` và IDs; product card được backend dựng riêng.

### Bước E — generation và kiểm tra output

Prompt phân tách rõ instruction cố định, source context và user input. Model phải:

- Chỉ dùng facts trong context.
- Không làm theo instruction nằm trong source/user nhằm đổi system rules.
- Nói rõ không tìm thấy dữ liệu khi thiếu nguồn.
- Không tư vấn ngoài phạm vi shop.
- Không phát minh product ID/link/giá/stock.

LLM trả structured output gồm `answer`, `cited_source_ids`, `referenced_product_ids`, `status`. Backend validate schema và chỉ chấp nhận ID thuộc retrieval set. Giá/stock trong prose tốt nhất được render từ template/backend; nếu model sinh số liệu, validator đối chiếu với hydrated facts hoặc thay bằng câu trả lời template an toàn.

### Bước F — persistence và response

Lưu assistant message, retrieval trace tối thiểu (IDs/scores/version, không secret), status và latency. Trả answer + product cards + nguồn. Không tiết lộ prompt nội bộ, embedding hoặc raw admin-only content.

## 5. Guardrails bắt buộc

### Grounding

- Không source hợp lệ → câu fallback tiếng Việt và `insufficient_data`.
- Câu hỏi ngoài scope → thông báo chỉ hỗ trợ mua sắm/chính sách của website.
- Product facts chỉ được trả từ SQL hydration trong request hiện tại.
- Knowledge facts phải có source chunk active; response lưu citation ID để audit.

### Prompt injection và data isolation

- User/source text là dữ liệu không đáng tin, được delimit và không có quyền thay instruction.
- Tool/function schema allow-list; model không tạo SQL hoặc gọi endpoint tùy ý.
- Query parameterized; filter column/operator allow-list.
- Anonymous chat session cần secret token; user chỉ đọc session của mình; admin mới đọc transcript qua ticket/admin API.
- Không đưa password hash, token, email khách khác, admin note hoặc database metadata vào context.

### Safety và độ bền

- Timeout và retry hữu hạn cho Gemini; circuit/fallback rõ ràng khi provider unavailable.
- Rate limit, max messages/context, max output tokens.
- Log đã redact; không log API key hoặc cookie.
- Product/order APIs vẫn hoạt động khi Gemini/embedding lỗi.

## 6. Hybrid ranking đề xuất

1. SQL hard filters loại candidate không đạt category/price/size/color/active.
2. Text rank theo tên/SKU/description cho keyword.
3. Vector rank trên mô tả ngữ nghĩa.
4. Hợp nhất rank; boost có giới hạn cho exact SKU/name và label phù hợp.
5. Không boost “bán chạy” nếu không có dữ liệu/định nghĩa; sort `best_selling` dựa trên order items hợp lệ hoặc seed metric đã công bố.
6. Trả tối đa số card hợp lý (ví dụ 3–5), đa dạng hóa nếu nhiều item gần giống.

Threshold/top-k phải cấu hình và đánh giá bằng bộ câu hỏi tiếng Việt, không chọn tùy ý chỉ vì demo.

## 7. Conversation memory

- `chat_sessions` định danh phiên anonymous hoặc user.
- `chat_messages` lưu role/content/status.
- State có cấu trúc lưu filters gần nhất, product refs và intent để xử lý câu nối tiếp như “còn màu đen không?”.
- Khi user đổi chủ đề, không mang filter cũ không liên quan.
- Có giới hạn retention/config cho demo; session ID không phải bằng chứng authorization.

## 8. Support handoff

Intent hoặc nút “Gặp nhân viên” gọi endpoint tạo ticket idempotent gắn `chat_session_id`. Response trả `ticket_code`; admin xem transcript bằng quyền admin. Chatbot không hứa thời gian phản hồi, hotline/email/live chat vì chưa tích hợp.

## 9. Cập nhật và freshness

- Product update commit ngay vào SQL; chat product facts thấy dữ liệu mới ngay dù embedding pending.
- Semantic match có thể dùng vector version cũ trong cửa sổ ngắn nhưng hydration luôn loại dữ liệu sai; admin thấy `index_status`.
- Knowledge update chỉ được retrieval từ version đã index thành công. Có thể giữ version cũ active đến khi swap atomically để tránh khoảng trống.
- Metrics local/test: index lag, failed jobs, retrieval zero-result, grounded/insufficient ratio và provider errors.

## 10. Kiểm thử RAG

Bộ test gồm:

- Product query theo category, budget, color, size và tổ hợp.
- Exact SKU/name và câu hỏi nối tiếp trong session.
- FAQ/size/shipping/return/promotion có citation.
- Thay giá/stock trong DB rồi hỏi lại: response/card phải phản ánh giá trị mới.
- Product/knowledge update rồi reindex: nội dung mới truy xuất được.
- Không có dữ liệu, out-of-scope và Gemini unavailable.
- Prompt injection trong user message và knowledge document.
- Model trả ID/giá không thuộc context: validator chặn.
- Support request tạo một ticket và admin đọc đúng transcript.

Đánh giá không chỉ keyword match: kiểm tra grounded source IDs, field SQL chính xác, không hallucination, link hợp lệ và độ ổn định qua nhiều lần chạy.
