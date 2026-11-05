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

const installRuntimeGuard = (page: Page, expectedHttpFailures: ExpectedHttpFailure[]) => {
  const errors: string[] = []
  const expectedConsoleStatuses: number[] = []

  page.on('pageerror', (error) => errors.push(`pageerror: ${error.message}`))
  page.on('console', (message) => {
    if (message.type() !== 'error') return

    const failedStatus = /status of (\d+) \(/.exec(message.text())?.[1]
    const expectedIndex = failedStatus
      ? expectedConsoleStatuses.indexOf(Number(failedStatus))
      : -1
    if (expectedIndex >= 0) {
      expectedConsoleStatuses.splice(expectedIndex, 1)
      return
    }
    errors.push(`console: ${message.text()}`)
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
      expectedConsoleStatuses.push(response.status())
      return
    }
    errors.push(`http: ${request.method()} ${response.url()} (${response.status()})`)
  })

  return () => {
    expect(errors, 'Trang tài khoản không được phát sinh lỗi runtime hoặc HTTP ngoài dự kiến').toEqual([])
    expect(expectedHttpFailures, 'Mọi lỗi HTTP dự kiến phải thực sự xảy ra').toEqual([])
    expect(expectedConsoleStatuses, 'Console error phải khớp đúng lỗi HTTP đã cho phép').toEqual([])
  }
}

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
