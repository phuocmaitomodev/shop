import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../stores/order-session', () => ({ useRememberedOrder: () => ({ __v_isRef: true, value: { order_code: 'DH-001', total: 270000, currency: 'VND', guest_lookup_token: 'lookup-secret-once', payment: { method: 'cod', status: 'cod_due', provider: 'demo', is_simulation: true } } }) }))
import OrderSuccessPage from '../pages/OrderSuccessPage.vue'

describe('OrderSuccessPage', () => {
  it('shows the guest lookup secret once with safe-storage guidance', () => {
    const wrapper = mount(OrderSuccessPage, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    expect(wrapper.text()).toContain('DH-001')
    expect(wrapper.text()).toContain('lookup-secret-once')
    expect(wrapper.text()).toContain('không lưu trong URL')
    expect(wrapper.text()).toContain('COD mô phỏng')
  })
})
