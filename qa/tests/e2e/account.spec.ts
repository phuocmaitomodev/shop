import { randomUUID } from 'node:crypto'
import { expect, test, type Page } from '@playwright/test'

const apiBaseURL = (process.env.QA_API_BASE_URL ?? 'http://localhost:8000/api/v1').replace(/\/$/, '')
const accountPassword = process.env.QA_ACCOUNT_PASSWORD ?? 'MatKhau-AnToan-123'
const accountCookieName = process.env.QA_ACCOUNT_COOKIE_NAME ?? 'shop_session'

type ExpectedHttpFailure = {
  method: string
  pathname: string
  status: number
}

type ExpectedConsoleFailure = Pick<ExpectedHttpFailure, 'pathname' | 'status'>

test.use({ trace: 'off' })

const installRuntimeGuard = (page: Page, expectedHttpFailures: ExpectedHttpFailure[]) => {
  const errors: string[] = []
  const expectedConsoleFailures: ExpectedConsoleFailure[] = []

  page.on('pageerror', (error) => errors.push(`pageerror: ${error.message}`))
  page.on('console', (message) => {
    if (message.type() !== 'error') return

    const failedStatus = Number(/status of (\d+) \(/.exec(message.text())?.[1])
    const location = message.location().url
    const pathname = location ? new URL(location).pathname : ''
    const expectedIndex = expectedConsoleFailures.findIndex((failure) => (
      failure.status === failedStatus && failure.pathname === pathname
    ))
    if (expectedIndex >= 0) {
      expectedConsoleFailures.splice(expectedIndex, 1)
      return
    }
    errors.push(`console: ${message.text()} at ${location || '<unknown>'}`)
  })
  page.on('requestfailed', (request) => {
    errors.push(`requestfailed: ${request.method()} ${request.url()} (${request.failure()?.errorText})`)
  })
  page.on('response', (response) => {
    if (response.status() < 400) return

    const request = response.request()
    const pathname = new URL(response.url()).pathname
    const expectedIndex = expectedHttpFailures.findIndex((failure) => (
      failure.method === request.method()
      && failure.pathname === pathname
      && failure.status === response.status()
    ))
    if (expectedIndex >= 0) {
      expectedHttpFailures.splice(expectedIndex, 1)
      expectedConsoleFailures.push({ pathname, status: response.status() })
      return
    }
    errors.push(`http: ${request.method()} ${response.url()} (${response.status()})`)
  })

  return () => {
    expect(errors, 'Trang tài khoản không được phát sinh lỗi runtime hoặc HTTP ngoài dự kiến').toEqual([])
    expect(expectedHttpFailures, 'Mọi lỗi HTTP dự kiến phải thực sự xảy ra').toEqual([])
    expect(expectedConsoleFailures, 'Console error phải khớp đúng endpoint/status HTTP đã cho phép').toEqual([])
  }
}

test('runtime guard không được dùng 401 dự kiến để che console 401 từ endpoint khác', () => {
  const listeners = new Map<string, Array<(value: unknown) => void>>()
  const fakePage = {
    on: (event: string, listener: (value: unknown) => void) => {
      listeners.set(event, [...(listeners.get(event) ?? []), listener])
    },
  } as unknown as Page
  const emit = (event: string, value: unknown) => {
    for (const listener of listeners.get(event) ?? []) listener(value)
  }
  const expectedHttpFailures: ExpectedHttpFailure[] = [{
    method: 'POST',
    pathname: '/api/v1/auth/login',
    status: 401,
  }]
  const assertRuntimeClean = installRuntimeGuard(fakePage, expectedHttpFailures)

  emit('response', {
    status: () => 401,
    url: () => 'http://localhost:8000/api/v1/auth/login',
    request: () => ({ method: () => 'POST' }),
  })
  emit('console', {
    type: () => 'error',
    text: () => 'Failed to load resource: the server responded with a status of 401 (Unauthorized)',
    location: () => ({ url: 'http://localhost:8000/api/v1/unrelated' }),
  })

  expect(assertRuntimeClean).toThrow(/unrelated/)
})

const storageSnapshot = async (page: Page) => page.evaluate(async () => ({
  local: Object.entries(localStorage),
  session: Object.entries(sessionStorage),
  indexedDB: typeof indexedDB.databases === 'function'
    ? (await indexedDB.databases()).map((database) => database.name ?? '')
    : [],
}))

test('@account khách chưa đăng nhập thấy CTA và API hồ sơ từ chối 401', async ({ page }) => {
  const expectedHttpFailures: ExpectedHttpFailure[] = [{
    method: 'GET',
    pathname: '/api/v1/account/profile',
    status: 401,
  }]
  const assertRuntimeClean = installRuntimeGuard(page, expectedHttpFailures)

  const profileResponse = page.waitForResponse((response) => (
    response.url() === `${apiBaseURL}/account/profile`
    && response.request().method() === 'GET'
  ))
  const documentResponse = await page.goto('/tai-khoan')

  expect(documentResponse?.ok()).toBe(true)
  expect((await profileResponse).status()).toBe(401)
  await expect(page.getByRole('heading', { level: 2, name: 'Bạn chưa đăng nhập' })).toBeVisible()
  await expect(page.getByTestId('login-cta')).toHaveAttribute('href', '/dang-nhap')
  await expect(page.locator('form.auth-card')).toHaveCount(0)
  expect(await storageSnapshot(page)).toEqual({ local: [], session: [], indexedDB: [] })
  assertRuntimeClean()
})

test('@account đăng nhập cookie, cập nhật bền vững và đăng xuất an toàn', async ({ page, request, context }, testInfo) => {
  const fixtureId = `${testInfo.project.name}-${randomUUID().slice(0, 8)}`
  const email = `account-${fixtureId}@example.com`
  const initialName = 'Khách Hàng E2E'
  const initialPhone = '0900000000'
  const updatedName = 'Nguyễn Văn QA'
  const updatedPhone = '0901 234 567'

  const registerResponse = await request.post(`${apiBaseURL}/auth/register`, {
    data: {
      email,
      password: accountPassword,
      full_name: initialName,
      phone: initialPhone,
    },
  })
  expect(registerResponse.status()).toBe(201)

  const expectedHttpFailures: ExpectedHttpFailure[] = [
    { method: 'POST', pathname: '/api/v1/auth/login', status: 401 },
    { method: 'GET', pathname: '/api/v1/account/profile', status: 401 },
  ]
  const assertRuntimeClean = installRuntimeGuard(page, expectedHttpFailures)

  await page.goto('/dang-nhap')
  await page.getByLabel('Email').fill(email.toUpperCase())
  await expect(page.getByLabel('Mật khẩu')).toHaveAttribute('type', 'password')
  await page.getByLabel('Mật khẩu').fill('MatKhau-Sai-123')
  const failedLogin = page.waitForResponse((response) => (
    response.url() === `${apiBaseURL}/auth/login`
    && response.request().method() === 'POST'
  ))
  await page.getByRole('button', { name: 'Đăng nhập' }).click()
  expect((await failedLogin).status()).toBe(401)
  await expect(page).toHaveURL(/\/dang-nhap$/)
  await expect(page.getByRole('alert')).toHaveText('Email hoặc mật khẩu không đúng.')
  expect(await context.cookies()).toEqual([])
  expect(await storageSnapshot(page)).toEqual({ local: [], session: [], indexedDB: [] })

  await page.getByLabel('Mật khẩu').fill(accountPassword)
  const loginResponsePromise = page.waitForResponse((response) => (
    response.url() === `${apiBaseURL}/auth/login`
    && response.request().method() === 'POST'
  ))
  await page.getByRole('button', { name: 'Đăng nhập' }).click()
  const loginResponse = await loginResponsePromise
  expect(loginResponse.status()).toBe(200)
  const loginBody = await loginResponse.json() as { data: Record<string, unknown> }
  expect(Object.keys(loginBody.data).sort()).toEqual([
    'email', 'full_name', 'id', 'is_active', 'phone', 'role',
  ])

  await expect(page).toHaveURL(/\/tai-khoan$/)
  await expect(page.getByRole('heading', { level: 1, name: 'Hồ sơ của tôi' })).toBeVisible()
  await expect(page.getByLabel('Email')).toHaveValue(email)
  await expect(page.getByLabel('Họ và tên')).toHaveValue(initialName)
  await expect(page.getByLabel('Số điện thoại')).toHaveValue(initialPhone)

  const accountCookie = (await context.cookies()).find((cookie) => cookie.name === accountCookieName)
  expect(accountCookie).toMatchObject({ httpOnly: true, sameSite: 'Lax' })
  expect(accountCookie?.value).toBeTruthy()
  expect(await storageSnapshot(page)).toEqual({ local: [], session: [], indexedDB: [] })

  const emailInput = page.getByLabel('Email')
  await expect(emailInput).toHaveAttribute('readonly', '')
  await expect(page.getByRole('button', { name: /đổi email/i })).toHaveCount(0)
  await page.getByLabel('Họ và tên').fill(`  ${updatedName}  `)
  await page.getByLabel('Số điện thoại').fill(`  ${updatedPhone}  `)
  const patchResponse = page.waitForResponse((response) => (
    response.url() === `${apiBaseURL}/account/profile`
    && response.request().method() === 'PATCH'
  ))
  await page.getByRole('button', { name: 'Lưu thay đổi' }).click()
  expect((await patchResponse).status()).toBe(200)
  await expect(page.getByRole('status')).toHaveText('Đã lưu thay đổi hồ sơ.')
  await expect(page.getByLabel('Họ và tên')).toHaveValue(updatedName)
  await expect(page.getByLabel('Số điện thoại')).toHaveValue(updatedPhone)
  await expect(emailInput).toHaveValue(email)

  await page.reload()
  await expect(page.getByLabel('Họ và tên')).toHaveValue(updatedName)
  await expect(page.getByLabel('Số điện thoại')).toHaveValue(updatedPhone)
  await expect(page.getByLabel('Email')).toHaveValue(email)
  expect(await storageSnapshot(page)).toEqual({ local: [], session: [], indexedDB: [] })

  const logoutResponse = page.waitForResponse((response) => (
    response.url() === `${apiBaseURL}/auth/logout`
    && response.request().method() === 'POST'
  ))
  await page.getByTestId('logout').click()
  expect((await logoutResponse).status()).toBe(200)
  await expect(page).toHaveURL(/\/dang-nhap$/)
  expect((await context.cookies()).find((cookie) => cookie.name === accountCookieName)).toBeUndefined()

  const deniedProfile = page.waitForResponse((response) => (
    response.url() === `${apiBaseURL}/account/profile`
    && response.request().method() === 'GET'
  ))
  await page.goto('/tai-khoan')
  expect((await deniedProfile).status()).toBe(401)
  await expect(page.getByRole('heading', { level: 2, name: 'Bạn chưa đăng nhập' })).toBeVisible()
  await expect(page.getByTestId('login-cta')).toHaveAttribute('href', '/dang-nhap')
  await expect(page.locator('form.auth-card')).toHaveCount(0)
  expect(await storageSnapshot(page)).toEqual({ local: [], session: [], indexedDB: [] })
  assertRuntimeClean()
})
