# QA automation foundation

Thư mục này chứa smoke test cho application shell và acceptance E2E của MVP catalog/chat RAG. Auth, cart, checkout, order, admin và support nằm ngoài release gate MVP hiện hành.

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
node node_modules/typescript/lib/tsc.js -p tsconfig.json --noEmit
npm run test:smoke

# Khi stack Compose đã chạy, migrate, seed và reindex xong:
QA_BASE_URL=http://127.0.0.1:5176 \
QA_API_BASE_URL=http://127.0.0.1:8000/api/v1 \
npm run test:mvp

# Policy API + widget citation trên desktop/mobile
npm run test:return-policy

# Toàn bộ case canonical_current trong corpus policy (chạy một lần qua API)
npm run test:return-policy:corpus
```

`test:return-policy:corpus` đọc trực tiếp
`fixtures/return-policy-questions.json` và fail khi direct, paraphrase,
follow-up, multi-fact, boundary hoặc prompt-injection regression thiếu fact/citation.
Script dùng `QA_API_BASE_URL`; không chạy lặp theo browser project.

Cấu hình mặc định dùng Google Chrome cài trên máy (`channel: chrome`). Nếu môi trường CI không có Chrome, chạy `npm run install:browsers` và đổi project sang Chromium bundled trong cấu hình CI tương ứng.

Để test một frontend đang chạy sẵn:

```bash
cd qa
QA_BASE_URL=http://127.0.0.1:5176 npm run test:smoke
```

## Biến môi trường integration

- `QA_API_BASE_URL`: mặc định `http://127.0.0.1:8000/api/v1`.
- `QA_ALLOW_DB_RESET=true`: khóa an toàn bắt buộc trước khi reset DB.
- `QA_DATABASE_RESET_COMMAND`: JSON argv array cho reset database test, ví dụ `["docker","compose","down","--volumes"]`.
- `QA_DATABASE_SEED_COMMAND`: JSON argv array cho seed deterministic.

Các helper destructive vẫn fail-closed: cần opt-in rõ, database test và command hợp lệ; suite E2E MVP không tự reset database đang chạy.

Lifecycle policy `seed → worker → API/orchestration → update/reindex → archive`
được kiểm tra trên PostgreSQL rỗng bởi
`backend/tests/integration/test_return_policy_lifecycle_postgres.py`. Test này nằm
trong service Compose `migration-test`; nó không mutate database E2E đang chạy.

Live Gemini smoke chỉ được chạy khi credential thật được cung cấp ngoài repository.
Không có credential thì phải ghi `SKIP`, không được tính là `PASS`; stub deterministic
và mocked structured-output vẫn là release gate bắt buộc.
