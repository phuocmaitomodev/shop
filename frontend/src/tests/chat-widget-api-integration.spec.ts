import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

const chatEnvelope = {
  data: {
    answer: 'Áo sơ mi linen xanh còn hàng.',
    products: [{
      id: '00000000-0000-0000-0000-000000000001',
      slug: 'ao-so-mi-linen-xanh',
      name: 'Áo sơ mi linen xanh',
      image_url: '/media/linen.jpg',
      effective_price: 459000,
      available_colors: ['Xanh'],
      available_sizes: ['M', 'L'],
      in_stock: true,
      url: '/san-pham/ao-so-mi-linen-xanh',
    }],
    sources: [],
    status: 'ok',
  },
  meta: { request_id: 'integration-request' },
}

describe('chat widget API integration', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('submits through the shared API client and renders the response contract', async () => {
    vi.resetModules()
    vi.stubEnv('VITE_API_BASE_URL', 'https://api.test/api/v1')
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(chatEnvelope), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)
    const { default: ChatWidget } = await import('../components/chat/ChatWidget.vue')
    const wrapper = mount(ChatWidget, {
      global: {
        stubs: {
          RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
        },
      },
    })

    await wrapper.get('[data-testid="chat-toggle"]').trigger('click')
    await wrapper.get('textarea').setValue('Tìm áo sơ mi linen xanh')
    await wrapper.get('form').trigger('submit')
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('https://api.test/api/v1/chat')
    expect(init).toMatchObject({ method: 'POST', credentials: 'include' })
    expect(JSON.parse(String(init.body))).toEqual({
      message: 'Tìm áo sơ mi linen xanh',
      history: [],
    })
    await vi.waitFor(() => expect(wrapper.get('[data-testid="chat-product-card"]').text())
      .toContain('Áo sơ mi linen xanh'))
  })

  it('posts confirmation credentials only after the user activates the typed confirm button', async () => {
    vi.resetModules()
    vi.stubEnv('VITE_API_BASE_URL', 'https://api.test/api/v1')
    const proposalEnvelope = {
      data: {
        answer: 'Vui lòng xác nhận hủy đơn.',
        products: [],
        sources: [],
        status: 'ok',
        proposed_action: {
          action: 'order_cancel',
          resource_code: 'DH-2026-0003',
          summary: 'Hủy đơn DH-2026-0003',
          requires_confirmation: true,
          confirmation_token: 'opaque-one-time-token',
          expires_at: '2099-11-03T04:05:00Z',
        },
      },
      meta: { request_id: 'proposal-request' },
    }
    const confirmedEnvelope = {
      data: {
        answer: 'Đã hủy đơn DH-2026-0003.',
        products: [],
        sources: [],
        status: 'ok',
        proposed_action: null,
      },
      meta: { request_id: 'confirm-request' },
    }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(proposalEnvelope), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify(confirmedEnvelope), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))
    vi.stubGlobal('fetch', fetchMock)
    const { default: ChatWidget } = await import('../components/chat/ChatWidget.vue')
    const wrapper = mount(ChatWidget)

    await wrapper.get('[data-testid="chat-toggle"]').trigger('click')
    await wrapper.get('textarea').setValue('Hủy đơn của tôi')
    await wrapper.get('form').trigger('submit')
    await vi.waitFor(() => expect(wrapper.find('[data-testid="chat-action-confirm"]').exists()).toBe(true))
    expect(fetchMock).toHaveBeenCalledTimes(1)

    await wrapper.get('[data-testid="chat-action-confirm"]').trigger('click')
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))

    const [, confirmationInit] = fetchMock.mock.calls[1] as [string, RequestInit]
    const confirmationBody = JSON.parse(String(confirmationInit.body))
    const confirmationHeaders = new Headers(confirmationInit.headers)
    expect(confirmationHeaders.get('Idempotency-Key')).toMatch(/^chat-action-/)
    expect(confirmationBody).toMatchObject({
      message: 'Xác nhận thao tác',
      history: [],
      confirmation_token: 'opaque-one-time-token',
    })
    expect(confirmationBody.client_message_id).toMatch(/^[0-9a-f-]{36}$/)
    expect(confirmationBody).not.toHaveProperty('action')
    expect(confirmationBody).not.toHaveProperty('resource_code')
    await vi.waitFor(() => expect(wrapper.get('[data-testid="chat-messages"]').text()).toContain('Đã hủy đơn'))
    wrapper.unmount()
  })
})
