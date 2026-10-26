import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiClientMock } = vi.hoisted(() => ({ apiClientMock: vi.fn() }))
vi.mock('../services/api-client', () => ({ apiClient: apiClientMock }))

import { sendChatMessage } from '../services/chat'

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
}

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
    expect(apiClientMock).toHaveBeenCalledWith('/chat', {
      method: 'POST',
      body: JSON.stringify({ message: 'Màu đen', history }),
    })
  })
})
