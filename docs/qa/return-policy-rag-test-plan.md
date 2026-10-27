# RET-QA-01 — Kế hoạch nghiệm thu RAG chính sách đổi trả

## 1. Phạm vi và nguồn sự thật

Kế hoạch này đặc tả corpus và oracle cho vertical slice `return_policy` qua `POST /api/v1/chat`. Nguồn sự thật theo thứ tự là `request.md`, `docs/mvp-product-rag-scope.md` mục 3.4, `docs/api-contract.md` và `docs/acceptance-test.md` mục 7.1. Không mở rộng sang CRUD knowledge, support ticket, live chat hoặc tích hợp Zalo.

Fixture machine-readable nằm tại `qa/fixtures/return-policy-questions.json`. Đây là dữ liệu bàn giao cho unit/integration/API/RAG evaluation; task này chưa tuyên bố implementation đã runnable hoặc RET-RAG-01..06 đã PASS.

## 2. Oracle canonical

Source hợp lệ duy nhất có:

- `title=Chính sách đổi trả`;
- `document_type=return_policy`, `locale=vi`, `is_active=true`;
- projection và chunk active, `index_status=indexed`, cùng `source_version` hiện hành.

Mọi fact trong answer phải là tập con đúng nghĩa của policy canonical:

- đổi trong **07 ngày**; trả/hoàn tiền trong **03 ngày**, đều tính từ giao hàng thành công;
- khách liên hệ shop trước khi gửi;
- hàng nguyên vẹn, chưa dùng/giặt/sửa, còn tem/tag, không bẩn/rách/hư/mùi lạ, đủ phụ kiện/quà và có mã đơn hoặc thông tin mua;
- shop kiểm tra trước khi duyệt; đổi size/màu/mẫu tùy tồn kho; hỗ trợ lỗi nhà sản xuất, hư vận chuyển và giao sai;
- các trường hợp loại trừ giữ đúng điều kiện canonical; hàng sale/thanh lý phụ thuộc thông báo lúc mua, không được kết luận tuyệt đối;
- đổi theo nhu cầu: khách chịu cả phí gửi về và phí giao hàng mới; lỗi nhà sản xuất/giao sai: shop chịu; hư vận chuyển: shop chịu sau khi xác nhận;
- liên hệ Mộc Store qua Zalo `0367962529` chỉ là text, không tạo action/integration/live chat.

Không dùng answer mẫu làm oracle. Không chấp nhận đảo 07/03 ngày, đổi mốc tính, tự thêm thời hạn xử lý, cam kết hoàn tiền, phí, điều kiện hoặc ngoại lệ không có trong source.

## 3. Oracle response và citation

### 3.1. Policy có dữ liệu hợp lệ

- intent nội bộ: `return_policy`;
- HTTP success envelope theo contract; `status=ok`;
- `products` bằng `[]` chính xác;
- answer chỉ chứa fact canonical phù hợp câu hỏi;
- có ít nhất một source retrieval đã validate;
- mọi source policy có `source_type=knowledge`, `knowledge_type=return_policy`, `product_id=null`, `title=Chính sách đổi trả`;
- `source_id`, `rag_document_id` và từng `chunk_id` phải thuộc retrieval set của chính request; `chunk_ids` không rỗng;
- không tạo URL policy từ UUID và không tạo product card.

### 3.2. Không có dữ liệu hợp lệ

Khi source/chunk rỗng, inactive, pending, failed, stale hoặc khác locale/type:

- `status=insufficient_data`;
- `products=[]`, `sources=[]`;
- answer fallback tiếng Việt không chứa fact policy như thể đã được xác minh;
- model không được dùng history, kiến thức nền hoặc version cũ để lấp dữ liệu.

### 3.3. Product và ngoài phạm vi

Product-only phải giữ route/semantics `product_search`; câu ngoài phạm vi phải `out_of_scope`. Các case này là regression intent boundary, không áp oracle `products=[]` của policy thành công.

## 4. Ma trận traceability

| Acceptance | Risk | Nhóm case fixture | Level/owner kế tiếp | Oracle bắt buộc |
|---|---|---|---|---|
| RET-RAG-01 | RET-RK-01 | `direct`, `paraphrase`, `follow_up`, `product_regression`, `out_of_scope`, `mixed_policy` | unit + API + RAG / RET-RAG-02, RET-QA-02 | allow-list intent; history policy rõ mới route follow-up; product/out-of-scope không bị policy chiếm route |
| RET-RAG-02 | RET-RK-02 | `canonical_seed` và setup `canonical_current` | integration / RET-BE-01, RET-QA-02 | đúng một source canonical; seed lặp không duplicate; verifier fail closed; current index hoàn tất |
| RET-RAG-03 | RET-RK-03 | `no_data`, `inactive`, `pending`, `failed`, `wrong_type`, `wrong_locale`, `stale` | unit + PostgreSQL integration + RAG / RET-RAG-01, RET-QA-02 | chỉ active/indexed/current/vi/return_policy; dedupe source/chunk; rank deterministic |
| RET-RAG-04 | RET-RK-04 | `deadline`, `washed`, `order_code`, `fees`, `sale`, `contact`, `multi_fact` | unit + API + RAG / RET-RAG-02, RET-QA-02 | fact subset; tách 07/03; phí hai chiều; sale có điều kiện; `products=[]`; IDs/chunks đúng |
| RET-RAG-05 | RET-RK-05 | `stale`, `conflicting_source`, `user_injection`, `source_injection`, `archive` | unit + integration + API + RAG / RET-RAG-01..02, RET-QA-02 | không trộn version; archive/empty fail closed; instruction được coi là data; không lộ prompt/secret |
| RET-RAG-06 | RET-RK-06 | toàn bộ policy success cộng `contact` và product regression | API + E2E desktop/mobile / RET-FE-01, RET-QA-02 | schema additive; citation chỉ title; không card/link policy; product UI giữ nguyên; không Zalo/live-chat action; console sạch |

## 5. Nhóm dữ liệu và setup

| Setup key | Trạng thái | Kết quả retrieval |
|---|---|---|
| `canonical_current` | source/projection/chunk active, indexed, locale vi, cùng current version | được phép dùng |
| `no_matching_chunks` | không candidate qua threshold | rỗng |
| `source_inactive` | canonical source archived/inactive | rỗng |
| `projection_pending` | projection current nhưng pending | rỗng |
| `projection_failed` | index current failed | rỗng |
| `wrong_type_or_locale` | FAQ hoặc locale khác vi | rỗng |
| `stale_only` | chỉ version cũ indexed; current version chưa indexed | rỗng, không fallback version cũ |
| `current_and_stale` | current indexed hợp lệ và version cũ còn record | chỉ current, không trộn |
| `conflicting_current_source` | source current chứa canonical facts kèm fact xung đột/instruction độc trong data | validator chỉ cho fact canonical đã cho phép hoặc fail closed |

ID runtime không hard-code UUID. Harness phải lấy IDs từ seed/setup, lưu retrieval set cho từng request, rồi đối chiếu response theo quan hệ thuộc tập.

## 6. Cách chạy corpus

1. Parse fixture và validate `schema_version`, ID duy nhất, acceptance mapping và fact IDs.
2. Chạy intent classifier/guardrail unit test cho toàn bộ case không cần DB.
3. Trên PostgreSQL test sạch: migrate → seed → verifier → index worker; chạy seed lại và so count/version/job.
4. Tạo từng setup negative trong transaction/namespace riêng; chạy retrieval và API; rollback hoặc reset sau case.
5. Với provider stub deterministic, assert đầy đủ status, fact IDs, products, sources và retrieval membership; đây là release gate.
6. Với Gemini có key ngoài repository, chạy cùng input ở profile `gemini_smoke`: không exact-match prose; assert predicate fact/citation, forbidden claim, products và status. Ghi riêng PASS/FAIL/SKIP; thiếu key là SKIP, không phải PASS.
7. E2E desktop 1366×768 và mobile 390×844 kiểm citation title, không policy URL/card/action giả, product regression, console/page/request error.

## 7. Quy tắc assertion cho answer

Harness nên chuẩn hóa text Unicode và dùng predicate ngữ nghĩa có kiểm soát thay vì snapshot nguyên câu:

- `required_fact_ids`: answer phải thể hiện tất cả fact được yêu cầu;
- `allowed_fact_ids`: mọi fact policy phát hiện trong answer phải thuộc canonical allow-list;
- `forbidden_claim_ids`: phát hiện đảo deadline, kết luận sale tuyệt đối, phí một chiều, tự duyệt, hoặc claim từ injection thì fail;
- case negative cấm mọi `canonical_fact_ids` trong answer, ngoại trừ câu fallback không khẳng định fact;
- số điện thoại chỉ được xuất hiện ở case hỏi liên hệ hoặc multi-fact có liên hệ, không biến thành URL/action;
- citation được kiểm bằng object và membership IDs, không chỉ tìm chuỗi title trong prose.

Gemini smoke phải dùng cùng factual predicates và citation assertions như stub; chỉ bỏ exact wording/order. Raw model output ngoài allow-list, malformed structured output hoặc citation không thuộc retrieval set phải bị orchestration đổi thành `insufficient_data`.

## 8. Entry, exit và evidence

Entry cho RET-QA-02: các commit RET-BE-01, RET-RAG-01, RET-RAG-02 và RET-FE-01 đã review; có command migrate/seed/verifier/index; test DB cô lập; stub deterministic; frontend/backend chạy đúng commit.

Exit:

- mọi case P0 applicable pass với stub trên clean run, không retry che flaky;
- seed/reseed và negative source state có evidence DB;
- source/chunk IDs được đối chiếu retrieval set; không chỉ so prose;
- API/widget desktop/mobile pass, product chat không regression;
- Gemini smoke được báo độc lập và chỉ PASS khi thực chạy có key;
- report ghi commit, commands, counts, environment, PASS/FAIL/SKIP, logs/traces khi fail.

Dừng gate nếu có fact policy bịa/sai, dùng stale/inactive/failed source, citation giả, lộ prompt/secret, policy có product card, hoặc product query bị đổi route.