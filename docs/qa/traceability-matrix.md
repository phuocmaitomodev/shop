# QA-01 — Traceability matrix

## 1. Quy ước

- Nguồn sự thật: `request.md`, sau đó là `docs/api-contract.md`, `docs/database-schema.md`, `docs/architecture.md`, `docs/rag-design.md` và `docs/acceptance-test.md`.
- Loại test: `U` unit, `I` integration, `API`, `E2E`, `RESP` responsive, `RAG` RAG evaluation.
- Trạng thái `Planned` nghĩa là chưa có implementation/dependency để chạy; không được tính PASS.
- `Automated partial` chỉ xác nhận phần foundation đang tồn tại, không xác nhận toàn bộ acceptance ID.
- Test runnable hiện tại:
  - `QA-E2E-SHELL-001`: application shell trên Chrome desktop 1366×768 và mobile 390×844.
  - `QA-E2E-ROUTES-001`: 25 route placeholder hiện tại và route 404, trên hai viewport.
  - Backend hiện có: 7 test config/health/migration metadata trong `backend/tests/`.
  - Frontend hiện có: 31 unit/component/router test trong `frontend/src/tests/`.

## 2. Yêu cầu gốc → tiêu chí nghiệm thu/test

Mỗi dòng dưới đây đại diện một yêu cầu có thể kiểm chứng trong `request.md`; yêu cầu ngoài phạm vi được kiểm tra theo hướng “không được tích hợp thật”.

| Requirement ID | Yêu cầu từ `request.md` | Acceptance IDs | Test dự kiến | Loại | Trạng thái |
|---|---|---|---|---|---|
| REQ-SYS-01 | Website tiếng Việt, tiền VND | CAT-20 | Locale/content và formatter tiền | U, E2E | Planned |
| REQ-SYS-02 | Chạy hoàn chỉnh local, desktop/mobile | BOOT-01, BOOT-02, UI-01 | Clean-room bootstrap và viewport suite | I, E2E, RESP | Planned; shell partial |
| REQ-CAT-01 | Trang chủ, danh mục, chi tiết sản phẩm | CAT-01, UI-04 | Điều hướng và API/catalog data | API, E2E | Placeholder automated partial |
| REQ-CAT-02 | Đúng 100 sản phẩm thuộc 7 nhóm | BOOT-05, CAT-01 | Seed verifier + category browse | I, API, E2E | Planned |
| REQ-CAT-03 | Product có tên/SKU/mô tả/category/giá/sale/ảnh/màu/size/stock | CAT-02 | Schema/API/UI field assertions | I, API, E2E | Planned |
| REQ-CAT-04 | Size S/M/L/XL, một số XXL | BOOT-06, CAT-02 | Seed distribution/variant assertions | I, API | Planned |
| REQ-CAT-05 | Mỗi product 2–4 màu; stock theo color-size | BOOT-06, CAT-07, ADM-04 | Seed constraints và variant CRUD | I, API, E2E | Planned |
| REQ-CAT-06 | Nhãn Mới/Bán chạy/Giảm giá | CAT-02, ADM-03 | Label seed/API/UI/CRUD | I, API, E2E | Planned |
| REQ-CAT-07 | Search tên/keyword | CAT-03 | Search exact/partial/empty/Unicode | U, API, E2E | Planned |
| REQ-CAT-08 | Filter category/price/size/color | CAT-04 | Filter đơn, tổ hợp và boundary | U, API, E2E | Planned |
| REQ-CAT-09 | Sort giá/newest/best-selling | CAT-05 | Stable sort và tie/boundary | U, API, E2E | Planned |
| REQ-CAT-10 | Related products có link hợp lệ | CAT-06, UI-03 | Related relevance và navigation | API, E2E | Planned |
| REQ-CAT-11 | Cart add theo variant/update/delete | CAT-07, CAT-08 | Cart CRUD và totals | U, API, E2E | Planned |
| REQ-CAT-12 | Revalidate giá/stock trước order | CAT-09, CAT-10 | Mutation giữa cart và checkout | I, API, E2E | Planned |
| REQ-CAT-13 | Guest checkout | CAT-15 | Guest COD happy path | API, E2E | Planned |
| REQ-CAT-14 | Register/login/logout/forgot/order history | CAT-13, CAT-14, CAT-18 | Auth/session/reset/ownership | API, E2E | Planned |
| REQ-CAT-15 | Chỉ email/password, không social login | CAT-13, SEC-02 | Auth contract và bundle/link audit | API, E2E | Planned |
| REQ-CAT-16 | Coupon apply/validate | CAT-11, CAT-12 | Rule matrix valid/expired/min/limits | U, I, API, E2E | Planned |
| REQ-CAT-17 | Responsive mobile-first/touch | UI-01, UI-02 | Viewport/touch matrix | RESP, E2E | Shell automated partial |
| REQ-ORD-01 | Checkout đúng 6 bước | CAT-15 | Guest/customer checkout journey | E2E | Planned |
| REQ-ORD-02 | COD hoàn chỉnh | CAT-15 | Transaction/order confirmation | I, API, E2E | Planned |
| REQ-ORD-03 | Online chỉ mô phỏng, không giao dịch thật | CAT-17 | Network/domain audit + notice | API, E2E | Planned |
| REQ-ORD-04 | Không tích hợp hãng vận chuyển thật | CAT-16, SEC-02 | Config/network audit | I, E2E | Planned |
| REQ-ORD-05 | Phí cố định và ngưỡng miễn phí từ config | CAT-16 | Below/at/above threshold | U, API, E2E | Planned |
| REQ-ORD-06 | Không gửi email thật | CAT-14, CAT-15 | Network/log audit | I, E2E | Planned |
| REQ-ORD-07 | Check stock lúc confirm | CAT-09, CAT-10 | Concurrent/last-item checkout | I, API, E2E | Planned |
| REQ-ORD-08 | Sáu trạng thái order | ADM-05, CAT-19 | State-machine table | U, API, E2E | Planned |
| REQ-ORD-09 | Chỉ cancel trước preparing, restore stock một lần | CAT-19 | Transition/idempotency/inventory | U, I, API, E2E | Planned |
| REQ-ADM-01 | Hai role customer/admin, admin account riêng | ADM-01 | RBAC route/API matrix | API, E2E | Planned |
| REQ-ADM-02 | Dashboard counts/revenue demo | ADM-02 | DB oracle so API/UI | I, API, E2E | Planned |
| REQ-ADM-03 | Product/image/category/price/label CRUD | ADM-03, ADM-10 | CRUD + media validation + storefront | API, E2E | Planned |
| REQ-ADM-04 | Variant color/size/stock CRUD | ADM-04 | Constraints và storefront reflection | I, API, E2E | Planned |
| REQ-ADM-05 | Order detail/status management | ADM-05 | Allowed/forbidden transitions | API, E2E | Planned |
| REQ-ADM-06 | Customer list/history; không đọc/sửa password | ADM-06, SEC-01 | Response schema/privacy/RBAC | API, E2E | Planned |
| REQ-ADM-07 | Coupon CRUD | ADM-07 | Rule CRUD và checkout reflection | API, E2E | Planned |
| REQ-ADM-08 | CRUD FAQ/size/shipping/return/promotion | ADM-08, RAG-12 | Content/version/reindex | I, API, E2E, RAG | Planned |
| REQ-ADM-09 | Support ticket list và transcript | ADM-09, RAG-15 | Ticket ownership/transcript | API, E2E | Planned |
| REQ-RAG-01 | Floating widget không che CTA | RAG-16, UI-01, UI-02 | Open/closed/scroll overlap | RESP, E2E | Position shell partial |
| REQ-RAG-02 | Trả lời product/size/shipping/return/promo/FAQ | RAG-01, RAG-02 | Vietnamese eval corpus | I, API, RAG | Planned |
| REQ-RAG-03 | Gợi ý theo need/type/budget/color/size | RAG-02 | Hard-filter oracle + relevance | API, RAG | Planned |
| REQ-RAG-04 | Product card đúng name/image/price/link | RAG-03, UI-03 | SQL oracle và link navigation | API, E2E, RAG | Planned |
| REQ-RAG-05 | Context chỉ trong cùng session | RAG-06, RAG-07 | Follow-up và cross-session isolation | API, RAG | Planned |
| REQ-RAG-06 | Persist transcript/session; anonymous chat | RAG-07, SEC-01 | DB/API ownership + token | I, API, E2E | Planned |
| REQ-RAG-07 | Chat tiếng Việt | RAG-01 | Corpus language assertion | RAG | Planned |
| REQ-RAG-08 | Dynamic price/promo/color/size/stock từ SQL | RAG-04, RAG-05 | Live mutation then query | I, API, RAG | Planned |
| REQ-RAG-09 | Knowledge dùng pgvector; hybrid SQL/vector | RAG-01, RAG-02 | Retrieval trace/source/filter | I, RAG | Planned |
| REQ-RAG-10 | Admin update tạo embedding/reindex | RAG-11, RAG-12 | Version swap/retry/freshness | I, API, RAG | Planned |
| REQ-RAG-11 | Gemini/embedding model qua env | BOOT-07, SEC-02 | Config/source/bundle scan | U, I | Planned |
| REQ-RAG-12 | Chỉ trả lời từ retrieved data | RAG-08, RAG-13 | Stub hallucination/unknown IDs | U, RAG | Planned |
| REQ-RAG-13 | Missing data fallback, không bịa | RAG-08 | Zero-result corpus | API, RAG | Planned |
| REQ-RAG-14 | Out-of-scope từ chối lịch sự | RAG-09 | Out-of-domain corpus | API, RAG | Planned |
| REQ-RAG-15 | Injection không đổi rule/lộ secret | RAG-10, SEC-02, SEC-03 | User/source injection corpus | U, API, RAG | Planned |
| REQ-SUP-01 | Request nhân viên tạo ticket gắn session | RAG-15, ADM-09 | Idempotency/linkage | I, API, E2E | Planned |
| REQ-SUP-02 | Widget trả ticket code | RAG-15 | Response/UI assertion | API, E2E | Planned |
| REQ-SUP-03 | Admin đọc đúng transcript | ADM-09, SEC-01 | Admin/other-user boundary | API, E2E | Planned |
| REQ-SUP-04 | Không live chat/Zalo/Facebook/email/hotline thật | RAG-15, SEC-02 | UI/network/integration audit | E2E | Planned |
| REQ-DATA-01 | Seed deterministic đúng 100 product Việt/VND | BOOT-04, BOOT-05, CAT-20 | Reset/seed/count/content | I, API | Planned |
| REQ-DATA-02 | Seed category/variant/price/stock tái tạo được | BOOT-06, BOOT-08 | Snapshot invariants after rerun | I | Planned |
| REQ-DATA-03 | Ảnh placeholder/stock hợp lệ lưu local | CAT-02, ADM-10, SEC-03 | URL/file/upload audit | I, API, E2E | Planned |
| REQ-DATA-04 | Seed size/FAQ/policies/promotion | BOOT-04, RAG-01 | DB verifier + retrieval eval | I, RAG | Planned |
| REQ-DATA-05 | Demo admin/customers, credential an toàn trong README/output | BOOT-04, BOOT-07, TECH-01 | Login + secret scan | I, API, E2E | Planned |
| REQ-UI-01 | Placeholder brand/logo; modern neutral theme | UI-01 | Visual/manual baseline | RESP, E2E | Shell partial |
| REQ-UI-02 | Header/menu/search/cart/account/footer/chat nhất quán | UI-01, UI-03 | Shared shell/link test | E2E, RESP | Automated partial |
| REQ-UI-03 | Không dead internal links | UI-03, UI-04 | Route crawl/status | E2E | Placeholder automated partial |
| REQ-UI-04 | Legal/contact/policies ghi rõ dữ liệu mẫu | CAT-20, UI-03 | Content assertion | E2E | Shell/footer partial |
| REQ-TECH-01 | Vue 3 + Vite, FastAPI, PostgreSQL+pgvector | BOOT-02, BOOT-03 | Build/compose/migration smoke | I | Foundation runnable partial |
| REQ-TECH-02 | Secrets/connections chỉ qua env; `.env.example` | BOOT-07, SEC-02 | Tracked-file/bundle/log scan | I | Planned full scan |
| REQ-TECH-03 | Migration, seed, README setup | BOOT-01, BOOT-03, BOOT-04, TECH-01 | Clean-room execution | I | Migration foundation only |
| REQ-SCOPE-01 | Không payment/refund/shipping/email/SMS/push/social/live-chat/external CRM thật | CAT-14, CAT-17, SEC-02 | Dependency/network/UI audit | I, E2E | Planned |
| REQ-SCOPE-02 | Không yêu cầu production/SSL/CDN/autoscaling/monitoring/legal approval | TECH-01 | README/scope review | Review | Planned |

## 3. Acceptance criteria → test dự kiến

| Acceptance ID | Test ID / mục tiêu | Loại | Ưu tiên | Trạng thái hiện tại |
|---|---|---|---|---|
| BOOT-01 | QA-BOOT-001 clean start theo README | I, E2E | P0 | Planned |
| BOOT-02 | QA-BOOT-002 Compose build/start/health; config parse | I | P0 | Config runnable; services planned full |
| BOOT-03 | QA-DB-001 migration trên DB trống/pgvector | I | P0 | Metadata unit partial; live DB planned |
| BOOT-04 | QA-DATA-001 seed fresh DB | I | P0 | Planned (BE-06 absent) |
| BOOT-05 | QA-DATA-002 assert product_count = 100 qua DB/admin API | I, API | P0 | Planned |
| BOOT-06 | QA-DATA-003 seed constraints/colors/sizes/SKU/orphans | I, API | P0 | Planned |
| BOOT-07 | QA-SEC-001 env/tracked secret/log scan | I | P0 | Planned full |
| BOOT-08 | QA-DATA-004 reset + reseed equivalence/idempotency | I | P1 | Planned |
| CAT-01 | QA-CAT-001 home/7 categories/detail | API, E2E | P0 | Routes only automated partial |
| CAT-02 | QA-CAT-002 all product fields match DB | I, API, E2E | P0 | Planned |
| CAT-03 | QA-CAT-003 name/keyword/Unicode/empty search | U, API, E2E | P0 | Planned |
| CAT-04 | QA-CAT-004 single/combined filters/boundaries | U, API, E2E | P0 | Planned |
| CAT-05 | QA-CAT-005 all sorts with deterministic oracle | U, API, E2E | P0 | Planned |
| CAT-06 | QA-CAT-006 related items and valid links | API, E2E | P1 | Planned |
| CAT-07 | QA-CAT-007 valid/inactive/out-of-stock variant selection | API, E2E | P0 | Planned |
| CAT-08 | QA-CART-001 cart add/update/delete/totals | U, API, E2E | P0 | Planned |
| CAT-09 | QA-STOCK-001 quantity boundaries | U, I, API, E2E | P0 | Planned |
| CAT-10 | QA-CHK-001 stale price/stock conflicts | I, API, E2E | P0 | Planned |
| CAT-11 | QA-COUPON-001 valid fixed/percent/cap totals | U, API, E2E | P0 | Planned |
| CAT-12 | QA-COUPON-002 invalid/expired/min/usage/active | U, API, E2E | P0 | Planned |
| CAT-13 | QA-AUTH-001 register/login/logout/session | API, E2E | P0 | Planned |
| CAT-14 | QA-AUTH-002 forgot/reset enumeration-safe/no email | API, E2E | P1 | Planned |
| CAT-15 | QA-CHK-002 six-step guest COD | I, API, E2E | P0 | Planned |
| CAT-16 | QA-PRICE-001 shipping below/at/above threshold | U, API, E2E | P0 | Planned |
| CAT-17 | QA-PAY-001 online-demo notice/no external call | API, E2E | P0 | Planned |
| CAT-18 | QA-ORDER-001 own history/detail only | API, E2E | P0 | Planned |
| CAT-19 | QA-ORDER-002 cancellation state/stock idempotency | U, I, API, E2E | P0 | Planned |
| CAT-20 | QA-LOC-001 Vietnamese/VND consistency | U, E2E | P1 | Planned |
| ADM-01 | QA-ADM-001 anonymous/customer/admin RBAC | API, E2E | P0 | Planned |
| ADM-02 | QA-ADM-002 dashboard DB oracle | I, API, E2E | P0 | Planned |
| ADM-03 | QA-ADM-003 product CRUD/storefront reflection | API, E2E | P0 | Planned |
| ADM-04 | QA-ADM-004 variant/stock constraints/CRUD | I, API, E2E | P0 | Planned |
| ADM-05 | QA-ADM-005 order transition matrix | U, API, E2E | P0 | Planned |
| ADM-06 | QA-ADM-006 customer privacy/no hash | API, E2E | P0 | Planned |
| ADM-07 | QA-ADM-007 coupon CRUD/checkout reflection | API, E2E | P0 | Planned |
| ADM-08 | QA-ADM-008 RAG content CRUD/index status | API, E2E, RAG | P0 | Planned |
| ADM-09 | QA-ADM-009 ticket/transcript integrity | API, E2E | P0 | Planned |
| ADM-10 | QA-MEDIA-001 MIME/size/path/reference validation | I, API, E2E | P1 | Planned |
| RAG-01 | QA-RAG-001 knowledge corpus + citations | API, RAG | P0 | Planned |
| RAG-02 | QA-RAG-002 product hard-filter corpus | API, RAG | P0 | Planned |
| RAG-03 | QA-RAG-003 cards hydrated from SQL/link | API, E2E, RAG | P0 | Planned |
| RAG-04 | QA-RAG-004 price live mutation | I, API, RAG | P0 | Planned |
| RAG-05 | QA-RAG-005 stock live mutation | I, API, RAG | P0 | Planned |
| RAG-06 | QA-RAG-006 follow-up/same vs other session | API, RAG | P0 | Planned |
| RAG-07 | QA-RAG-007 anonymous token/session ownership | API, E2E | P0 | Planned |
| RAG-08 | QA-RAG-008 missing data fallback | API, RAG | P0 | Planned |
| RAG-09 | QA-RAG-009 out-of-scope corpus | API, RAG | P0 | Planned |
| RAG-10 | QA-RAG-010 user/source prompt injection | U, API, RAG | P0 | Planned |
| RAG-11 | QA-RAG-011 product reindex/version freshness | I, API, RAG | P0 | Planned |
| RAG-12 | QA-RAG-012 knowledge reindex/inactive/version swap | I, API, RAG | P0 | Planned |
| RAG-13 | QA-RAG-013 stub hallucinated ID/price validator | U, RAG | P0 | Planned |
| RAG-14 | QA-RAG-014 provider timeout/error isolation | I, API, RAG | P1 | Planned |
| RAG-15 | QA-RAG-015 idempotent handoff/ticket/transcript | I, API, E2E | P0 | Planned |
| RAG-16 | QA-RESP-CHAT-001 widget open/closed/scroll overlap | E2E, RESP | P1 | Position only automated partial |
| UI-01 | QA-RESP-001 viewport matrix/no overflow-overlap | E2E, RESP | P0 | Shell 1366×768 + 390×844 partial |
| UI-02 | QA-RESP-002 touch targets/menu/cart/chat | E2E, RESP | P0 | Mobile menu smoke partial |
| UI-03 | QA-LINK-001 internal link crawl | E2E | P0 | Current shell/routes partial |
| UI-04 | QA-HTTP-001 page/assets/API status | API, E2E | P0 | Current route responses partial |
| UI-05 | QA-CONSOLE-001 no console/page/request errors | E2E | P0 | Current smoke automated |
| UI-06 | QA-STATE-001 loading/error/empty/network degradation | U, E2E | P1 | Planned |
| SEC-01 | QA-SEC-002 resource ownership ID substitution | I, API | P0 | Planned |
| SEC-02 | QA-SEC-003 repo/bundle/log/network secret scan | I, E2E | P0 | Planned |
| SEC-03 | QA-SEC-004 SQL/XSS/upload input corpus | U, I, API, E2E | P0 | Planned |
| TECH-01 | QA-DOC-001 README clean-room checklist | I | P0 | Planned |

## 4. Gate cập nhật matrix

Khi một vertical slice được bàn giao, QA phải thay `Planned` bằng test file/case cụ thể, chạy test thật và ghi evidence. Không đổi sang PASS chỉ vì route placeholder tồn tại hoặc helper compile được. Full acceptance chỉ đạt khi oracle DB/API/UI/RAG tương ứng đều sẵn sàng và P0 pass trên clean run.
