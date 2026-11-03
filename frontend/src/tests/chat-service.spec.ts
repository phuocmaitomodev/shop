import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiClientMock } = vi.hoisted(() => ({ apiClientMock: vi.fn() }))
vi.mock('../services/api-client', () => ({ apiClient: apiClientMock }))

import { sendChatMessage } from '../services/chat'
import type { ChatResponse } from '../types/chat'

const response = {
  answer: 'Áo thun đen còn hàng, giá 249.000 ₫.',
  products: [{
    id: '00000000-0000-0000-0000-000000000001',
    slug: 'ao-thun-den',
    name: 'Áo thun đen',
    image_url: '/media/ao.svg',
    effective_price: 249000,
    available_colors: ['Đen'],
    available_sizes: ['M'],
    in_stock: true,
    url: '/san-pham/ao-thun-den',
  }],
  sources: [],
  status: 'ok' as const,
  proposed_action: {
    action: 'order_cancel',
    resource_code: 'DH-2026-0001',
    summary: 'Hủy đơn DH-2026-0001',
    requires_confirmation: true as const,
    confirmation_token: 'opaque-one-time-token',
    expires_at: '2026-11-03T04:00:00Z',
  },
} satisfies ChatResponse

describe('chat service', () => {
  beforeEach(() => {
    apiClientMock.mockReset()
  })

  it('posts the bounded conversation contract and unwraps the success envelope', async () => {
    apiClientMock.mockResolvedValue({ data: response, meta: { request_id: 'request-1' } })
    const history = [
      { role: 'user' as const, content: 'Tôi cần áo size M' },
      { role: 'assistant' as const, content: 'Bạn thích màu nào?' },
    ]

    await expect(sendChatMessage('  Màu đen  ', history)).resolves.toEqual(response)
    expect(response.proposed_action?.requires_confirmation).toBe(true)
    expect(apiClientMock).toHaveBeenCalledWith('/chat', {
      method: 'POST',
      body: JSON.stringify({ message: 'Màu đen', history }),
    })
  })

  it('keeps proposed_action null for a read-only answer', async () => {
    const readOnlyResponse: ChatResponse = {
      ...response,
      proposed_action: null,
    }
    apiClientMock.mockResolvedValue({ data: readOnlyResponse, meta: { request_id: 'request-read' } })

    await expect(sendChatMessage('Chính sách đổi trả')).resolves.toMatchObject({
      proposed_action: null,
    })
  })
})
