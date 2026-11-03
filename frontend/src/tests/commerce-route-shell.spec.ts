import { mount } from '@vue/test-utils'
import { createMemoryHistory } from 'vue-router'
import { describe, expect, it } from 'vitest'

import CommerceAsyncState from '../components/commerce/CommerceAsyncState.vue'
import CommerceRouteShell from '../pages/CommerceRouteShell.vue'
import { createAppRouter } from '../router'

Object.defineProperty(window, 'scrollTo', { value: () => undefined, writable: true })

const commerceRoutes = [
  '/gio-hang',
  '/thanh-toan',
  '/dat-hang-thanh-cong',
  '/tra-cuu-don-hang',
  '/don-hang/DH-001/thanh-toan-demo',
  '/don-hang/DH-001/hoan-tien-demo',
]

describe('commerce route shells', () => {
  it.each(commerceRoutes)('resolves %s to the commerce shell', (path) => {
    const router = createAppRouter(createMemoryHistory())
    const resolved = router.resolve(path)

    expect(resolved.name).not.toBe('not-found')
    expect(resolved.matched[0]?.components?.default).toBe(CommerceRouteShell)
  })

  it('labels payment and refund routes as simulation-only', async () => {
    const router = createAppRouter(createMemoryHistory())
    await router.push('/don-hang/DH-001/hoan-tien-demo')
    await router.isReady()

    const wrapper = mount(CommerceRouteShell, { global: { plugins: [router] } })

    expect(wrapper.text()).toContain('mô phỏng')
    expect(wrapper.text()).toContain('Không có giao dịch hoàn tiền thật')
    expect(wrapper.get('[role="status"]').text()).toContain('Chưa có dữ liệu')
  })

  it.each([
    ['loading', 'Đang tải dữ liệu', 'status'],
    ['error', 'Không thể tải dữ liệu', 'alert'],
    ['empty', 'Chưa có dữ liệu', 'status'],
  ] as const)('renders the %s state accessibly', (state, expected, role) => {
    const wrapper = mount(CommerceAsyncState, { props: { state } })

    expect(wrapper.get(`[role="${role}"]`).text()).toContain(expected)
  })
})
