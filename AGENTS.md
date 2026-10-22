# AGENTS.md

## Mục đích

File này là quy ước chung cho mọi profile/agent làm việc trong repository `shop`. Mọi profile phải đọc `request.md`, `AGENTS.md` và các tài liệu liên quan trong `docs/` trước khi thay đổi dự án.

## Nguồn sự thật và thứ tự ưu tiên

1. Yêu cầu trực tiếp hiện tại của người dùng.
2. `request.md` — phạm vi và tiêu chí nghiệm thu gốc; không tự ý sửa.
3. `docs/api-contract.md` và `docs/database-schema.md` — hợp đồng tích hợp.
4. `docs/architecture.md`, `docs/rag-design.md`, `docs/acceptance-test.md`.
5. `docs/task-breakdown.md` — phân công, dependency và thứ tự triển khai.

Nếu tài liệu mâu thuẫn, dừng phần bị ảnh hưởng, ghi rõ mâu thuẫn và yêu cầu profile điều phối quyết định; không tự suy diễn rồi âm thầm đổi contract.

## Nguyên tắc chung

- Chỉ thay đổi file thuộc phạm vi task được giao; không sửa phần của profile khác nếu chưa phối hợp.
- Không thay đổi `request.md`.
- Không commit API key, secret, mật khẩu thật, token, dữ liệu cá nhân hoặc chuỗi kết nối thật.
- Dùng biến môi trường cho cấu hình; chỉ commit `.env.example` với giá trị giả/an toàn.
- Giao diện, dữ liệu demo và nội dung chatbot dùng tiếng Việt; tiền tệ là VND.
- Giữ đúng phạm vi demo: không tích hợp thanh toán, vận chuyển, email/SMS, social login hay live-chat thật.
- Dữ liệu động như giá, khuyến mãi, màu, size và tồn kho phải lấy từ PostgreSQL; không lấy giá trị hiện hành từ vector hoặc để LLM tự tạo.
- Các thay đổi database phải đi qua migration; dữ liệu demo phải tái tạo được bằng seed.
- Không hard-code tên model Gemini/embedding; cấu hình qua biến môi trường.
- Ưu tiên giải pháp đơn giản, có thể chạy local bằng Docker Compose; tránh thiết kế production ngoài phạm vi.
- Mọi link nội bộ phải có đích hợp lệ; widget chat không được che CTA trên desktop/mobile.
- Không log secret, mật khẩu, refresh token hoặc toàn bộ dữ liệu nhạy cảm của người dùng.

## Ranh giới trách nhiệm

### `shop-backend`

Sở hữu FastAPI, migration/seed, nghiệp vụ bán hàng, auth/RBAC, admin API, checkout, tồn kho và OpenAPI. Không tự đổi contract đã công bố mà không cập nhật tài liệu và thông báo frontend/RAG/QA.

### `shop-frontend`

Sở hữu Vue 3 + Vite, storefront, admin UI, cart/checkout, auth UI và vỏ widget chat. Chỉ gọi API theo `docs/api-contract.md`; không nhúng trực tiếp logic SQL, Gemini key hoặc secret vào trình duyệt.

### `shop-rag`

Sở hữu ingestion/chunking/embedding, hybrid retrieval, orchestration Gemini, guardrails, chat session và support handoff phía dịch vụ. Mọi giá/tồn kho/khuyến mãi xuất hiện trong câu trả lời phải được hydrate lại từ SQL tại thời điểm trả lời.

### `shop-qa`

Sở hữu test plan, fixture/automation, kiểm thử API/UI/RAG, kiểm tra responsive, console và báo cáo lỗi. QA không nới lỏng acceptance criteria để làm test pass.

## Quy tắc phối hợp

- Contract-first: schema và API liên quan phải được thống nhất trước khi frontend/RAG phụ thuộc vào chúng.
- Một task chỉ bắt đầu khi dependency trong `docs/task-breakdown.md` đã hoàn tất hoặc có mock/contract được điều phối chấp thuận.
- Khi đổi API/schema: cập nhật tài liệu tương ứng, migration/OpenAPI, consumer và test trong cùng thay đổi hoặc ghi rõ kế hoạch chuyển tiếp.
- Dùng mã lỗi ổn định, không bắt frontend phân tích nội dung message để xác định lỗi.
- Mọi lỗi/PR/handoff phải nêu: phạm vi, file thay đổi, migration/config mới, cách chạy test, kết quả thực tế và rủi ro còn lại.
- Không ghi đè thay đổi chưa commit của profile khác. Trước và sau task phải kiểm tra `git status` và diff của chính mình.

## Chất lượng và Definition of Done

Một task chỉ hoàn tất khi:

- Đáp ứng acceptance criteria tương ứng và không vượt phạm vi.
- Có test phù hợp (unit/integration/e2e hoặc contract test) và đã chạy thực tế.
- Migration/seed có thể chạy lại trên database mới nếu task chạm dữ liệu.
- API/schema/config/documentation được đồng bộ.
- Không có secret thật; không có lỗi nghiêm trọng trong log hoặc browser console ở luồng liên quan.
- Có hướng dẫn xác minh ngắn và bằng chứng kết quả test trong handoff.

## Quy ước Git

- Tách commit theo thay đổi logic, không trộn refactor ngoài phạm vi.
- Gợi ý prefix: `feat:`, `fix:`, `test:`, `docs:`, `chore:`.
- Không force-push, rebase hoặc xóa nhánh dùng chung nếu chưa được yêu cầu rõ ràng.
- Không commit file IDE, cache, build output, database local hoặc media tạm.
