import { expect, test } from '@playwright/test'

const placeholderRoutes = [
  ['/danh-muc/ao-thun', 'Danh mục sản phẩm'],
  ['/gio-hang', 'Giỏ hàng'],
  ['/thanh-toan', 'Thanh toán'],
  ['/dat-hang-thanh-cong', 'Đặt hàng thành công'],
  ['/dang-nhap', 'Đăng nhập'],
  ['/dang-ky', 'Đăng ký'],
  ['/quen-mat-khau', 'Quên mật khẩu'],
  ['/dat-lai-mat-khau', 'Đặt lại mật khẩu'],
  ['/tai-khoan', 'Tài khoản'],
  ['/tai-khoan/don-hang', 'Đơn hàng của tôi'],
  ['/tai-khoan/don-hang/DH-001', 'Chi tiết đơn hàng'],
  ['/admin', 'Quản trị cửa hàng'],
  ['/admin/san-pham', 'Quản lý sản phẩm'],
  ['/admin/don-hang', 'Quản lý đơn hàng'],
  ['/admin/khach-hang', 'Quản lý khách hàng'],
  ['/admin/ma-giam-gia', 'Quản lý mã giảm giá'],
  ['/admin/noi-dung-rag', 'Quản lý nội dung RAG'],
  ['/admin/ho-tro', 'Yêu cầu hỗ trợ'],
  ['/gioi-thieu', 'Giới thiệu'],
  ['/lien-he', 'Liên hệ'],
  ['/chinh-sach-giao-hang', 'Chính sách giao hàng'],
  ['/chinh-sach-doi-tra', 'Chính sách đổi trả'],
  ['/cau-hoi-thuong-gap', 'Câu hỏi thường gặp'],
] as const

let runtimeErrors: string[]

test.beforeEach(async ({ page }) => {
  runtimeErrors = []
  page.on('pageerror', (error) => runtimeErrors.push(`pageerror: ${error.message}`))
  page.on('console', (message) => {
    if (message.type() === 'error') runtimeErrors.push(`console: ${message.text()}`)
  })
  page.on('requestfailed', (request) => {
    runtimeErrors.push(`requestfailed: ${request.method()} ${request.url()} (${request.failure()?.errorText})`)
  })
})

test.afterEach(() => {
  expect(runtimeErrors, 'Trang không được phát sinh lỗi runtime, console hoặc request').toEqual([])
})

test('@smoke application shell hiển thị các landmark và CTA hiện có', async ({ page }) => {
  const response = await page.goto('/')

  expect(response?.ok()).toBe(true)
  await expect(page).toHaveTitle('Trang chủ | Mộc Store')
  await expect(page.getByRole('banner')).toContainText('Mộc Store')
  const primaryNavigation = page.locator('nav[aria-label="Điều hướng chính"]')
  await expect(primaryNavigation).toBeAttached()
  if ((page.viewportSize()?.width ?? 0) < 768) {
    await page.getByRole('button', { name: 'Mở hoặc đóng điều hướng' }).click()
  }
  await expect(primaryNavigation).toBeVisible()
  await expect(page.getByRole('search')).toBeVisible()
  await expect(page.getByRole('main')).toContainText('Khám phá phong cách của riêng bạn')
  await expect(page.getByRole('contentinfo')).toContainText('Dữ liệu cửa hàng mẫu')
  await expect(page.getByTestId('chat-widget-position')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Xem sản phẩm' })).toHaveAttribute('href', '/san-pham')
})

for (const [path, heading] of placeholderRoutes) {
  test(`@smoke route placeholder ${path} trả application shell và heading đúng`, async ({ page }) => {
    const response = await page.goto(path)

    expect(response?.ok()).toBe(true)
    await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Về trang chủ' })).toHaveAttribute('href', '/')
    await expect(page.getByTestId('chat-widget-position')).toBeVisible()
  })
}

test('@smoke route không tồn tại hiển thị trang 404 trong shell', async ({ page }) => {
  const response = await page.goto('/khong-ton-tai')

  expect(response?.ok()).toBe(true)
  await expect(page.getByRole('heading', { level: 1, name: 'Không tìm thấy trang' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Về trang chủ' })).toHaveAttribute('href', '/')
})
