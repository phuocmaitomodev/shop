import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  login: vi.fn(),
  getAccountProfile: vi.fn(),
  updateAccountProfile: vi.fn(),
  logout: vi.fn(),
  accountErrorMessage: vi.fn(() => 'Thông báo lỗi ổn định.'),
  isAuthenticationRequired: vi.fn(() => false),
  push: vi.fn(),
}))

vi.mock('../services/auth-account', () => ({
  login: mocks.login,
  getAccountProfile: mocks.getAccountProfile,
  updateAccountProfile: mocks.updateAccountProfile,
  logout: mocks.logout,
  accountErrorMessage: mocks.accountErrorMessage,
  isAuthenticationRequired: mocks.isAuthenticationRequired,
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: mocks.push }) }))

import AccountPage from '../pages/AccountPage.vue'
import LoginPage from '../pages/LoginPage.vue'

const customer = {
  id: 'customer-1',
  email: 'an@example.com',
  full_name: 'Nguyễn An',
  phone: '0900000000',
  role: 'customer' as const,
  is_active: true,
}

const routerLinkStub = { template: '<a :href="to"><slot /></a>', props: ['to'] }

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.accountErrorMessage.mockReturnValue('Thông báo lỗi ổn định.')
    mocks.isAuthenticationRequired.mockReturnValue(false)
  })

  it('submits email/password, disables duplicate submission, and redirects customers', async () => {
    let resolveLogin!: (profile: typeof customer) => void
    mocks.login.mockReturnValue(new Promise((resolve) => { resolveLogin = resolve }))
    const wrapper = mount(LoginPage)

    await wrapper.get('#login-email').setValue('an@example.com')
    await wrapper.get('#login-password').setValue('secret123')
    await wrapper.get('form').trigger('submit')

    expect(mocks.login).toHaveBeenCalledWith({ email: 'an@example.com', password: 'secret123' })
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('button[type="submit"]').text()).toContain('Đang đăng nhập')

    resolveLogin(customer)
    await flushPromises()
    expect(mocks.push).toHaveBeenCalledWith({ name: 'account' })
  })

  it('shows a stable mapped API error and restores the submit button', async () => {
    const failure = new Error('backend detail must not render')
    mocks.login.mockRejectedValue(failure)
    const wrapper = mount(LoginPage)

    await wrapper.get('#login-email').setValue('an@example.com')
    await wrapper.get('#login-password').setValue('wrong')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(mocks.accountErrorMessage).toHaveBeenCalledWith(failure)
    expect(wrapper.get('[role="alert"]').text()).toBe('Thông báo lỗi ổn định.')
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeUndefined()
  })
})

describe('AccountPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.accountErrorMessage.mockReturnValue('Thông báo lỗi ổn định.')
    mocks.isAuthenticationRequired.mockReturnValue(false)
  })

  it('loads the live profile and keeps email read-only', async () => {
    mocks.getAccountProfile.mockResolvedValue(customer)
    const wrapper = mount(AccountPage, { global: { stubs: { RouterLink: routerLinkStub } } })

    expect(wrapper.get('[role="status"]').text()).toContain('Đang tải')
    await flushPromises()

    expect(wrapper.get('#account-email').attributes('readonly')).toBeDefined()
    expect((wrapper.get('#account-email').element as HTMLInputElement).value).toBe('an@example.com')
    expect((wrapper.get('#account-full-name').element as HTMLInputElement).value).toBe('Nguyễn An')
    expect((wrapper.get('#account-phone').element as HTMLInputElement).value).toBe('0900000000')
  })

  it('updates editable fields and announces success', async () => {
    mocks.getAccountProfile.mockResolvedValue(customer)
    mocks.updateAccountProfile.mockResolvedValue({ ...customer, full_name: 'Nguyễn An Mới', phone: null })
    const wrapper = mount(AccountPage, { global: { stubs: { RouterLink: routerLinkStub } } })
    await flushPromises()

    await wrapper.get('#account-full-name').setValue('Nguyễn An Mới')
    await wrapper.get('#account-phone').setValue('')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(mocks.updateAccountProfile).toHaveBeenCalledWith({ full_name: 'Nguyễn An Mới', phone: null })
    expect(wrapper.get('[role="status"]').text()).toContain('Đã lưu thay đổi')
  })

  it('offers login instead of protected data when the profile request is unauthenticated', async () => {
    const failure = new Error('unauthenticated')
    mocks.getAccountProfile.mockRejectedValue(failure)
    mocks.isAuthenticationRequired.mockReturnValue(true)
    const wrapper = mount(AccountPage, { global: { stubs: { RouterLink: routerLinkStub } } })
    await flushPromises()

    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.get('[data-testid="login-cta"]').attributes('href')).toBe('/dang-nhap')
  })

  it('shows a retryable load error and loads the profile on retry', async () => {
    mocks.getAccountProfile
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce(customer)
    const wrapper = mount(AccountPage, { global: { stubs: { RouterLink: routerLinkStub } } })
    await flushPromises()

    expect(wrapper.get('[role="alert"]').text()).toContain('Thông báo lỗi ổn định')
    await wrapper.get('[data-testid="profile-retry"]').trigger('click')
    await flushPromises()

    expect(mocks.getAccountProfile).toHaveBeenCalledTimes(2)
    expect(wrapper.find('#account-email').exists()).toBe(true)
  })

  it('logs out through the API and returns to login', async () => {
    mocks.getAccountProfile.mockResolvedValue(customer)
    mocks.logout.mockResolvedValue(undefined)
    const wrapper = mount(AccountPage, { global: { stubs: { RouterLink: routerLinkStub } } })
    await flushPromises()

    await wrapper.get('[data-testid="logout"]').trigger('click')
    await flushPromises()

    expect(mocks.logout).toHaveBeenCalledOnce()
    expect(mocks.push).toHaveBeenCalledWith({ name: 'login' })
  })
})
