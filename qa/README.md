# QA automation foundation

Thư mục này thuộc QA-02 và chỉ tự động hóa những hành vi đã tồn tại: FE-01 application shell, route placeholder và trang 404. Các luồng catalog, auth, cart, checkout, admin, seed và RAG vẫn là test case planned trong traceability matrix; chưa có test giả đánh dấu pass.

## Cấu trúc

- `tests/e2e/`: Playwright E2E runnable.
- `helpers/api.ts`: factory API context và assertion error envelope cho API integration sau này.
- `helpers/database.ts`: guard reset/seed và oracle cho seed snapshot; chỉ dùng khi backend công bố command/query thật.
- `playwright.config.ts`: Chromium desktop 1366×768 và mobile 390×844; tự chạy frontend production preview nếu không đặt `QA_BASE_URL`.

## Chạy smoke test

Frontend phải được build trước vì Playwright dùng `vite preview`:

```bash
cd frontend
npm ci
npm run build
cd ../qa
npm ci
npm run test:smoke
```

Cấu hình mặc định dùng Google Chrome cài trên máy (`channel: chrome`). Nếu môi trường CI không có Chrome, chạy `npm run install:browsers` và đổi project sang Chromium bundled trong cấu hình CI tương ứng.

Để test một frontend đang chạy sẵn:

```bash
cd qa
QA_BASE_URL=http://127.0.0.1:5176 npm run test:smoke
```

## Biến môi trường dành cho integration sau này

- `QA_API_BASE_URL`: mặc định `http://127.0.0.1:8000/api/v1`.
- `QA_ALLOW_DB_RESET=true`: khóa an toàn bắt buộc trước khi reset DB.
- `QA_DATABASE_RESET_COMMAND`: JSON argv array cho reset database test do backend bàn giao, ví dụ `["docker","compose","down","--volumes"]`.
- `QA_DATABASE_SEED_COMMAND`: JSON argv array cho seed deterministic do backend bàn giao.

Không đặt command reset/seed mặc định ở QA-02 vì BE-06 chưa tồn tại. Helper phải fail rõ thay vì giả vờ seed thành công.
