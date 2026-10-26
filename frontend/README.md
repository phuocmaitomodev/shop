# Frontend Mộc Store

Vue 3 + Vite + TypeScript cho giao diện storefront, khu vực tài khoản, trang quản trị và vỏ chatbot.

## Chạy local

```bash
cp .env.example .env
npm install
npm run dev
```

Mặc định frontend chạy tại `http://localhost:5176` và gọi API theo `VITE_API_BASE_URL`.

## Kiểm tra

```bash
npm test
npm run build
```

FE-01 chỉ cung cấp application shell, route placeholder, API client và design tokens. Các nghiệp vụ catalog, auth, cart, checkout, admin và chatbot được triển khai ở các task tiếp theo.
