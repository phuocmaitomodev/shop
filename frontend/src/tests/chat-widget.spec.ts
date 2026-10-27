import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { sendChatMessageMock } = vi.hoisted(() => ({ sendChatMessageMock: vi.fn() }))
vi.mock('../services/chat', () => ({ sendChatMessage: sendChatMessageMock }))

import ChatWidget from '../components/chat/ChatWidget.vue'

describe('ChatWidget', () => {
  beforeEach(() => {
    sendChatMessageMock.mockReset()
  })

  it('opens from a touch-sized labelled button and closes with Escape', async () => {
    const wrapper = mount(ChatWidget, {
      attachTo: document.body,
      global: {
        stubs: {
          RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
        },
      },
    })
    const toggle = wrapper.get('[data-testid="chat-toggle"]')

    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)

    await toggle.trigger('click')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('[role="dialog"]').attributes('aria-label')).toBe('Trợ lý sản phẩm')

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
    expect(document.activeElement).toBe(toggle.element)

    wrapper.unmount()
  })

  it('sends a Vietnamese question and renders the grounded answer with product cards', async () => {
    sendChatMessageMock.mockResolvedValue({
      answer: 'Áo thun đen còn hàng, giá 249.000 ₫.',
      products: [{
        id: 'product-1',
        slug: 'ao-thun-den',
        name: 'Áo thun đen',
        image_url: null,
        effective_price: 249000,
        available_colors: ['Đen'],
        available_sizes: ['M'],
        in_stock: true,
        url: '/san-pham/ao-thun-den',
      }],
      sources: [],
      status: 'ok',
    })
    const wrapper = mount(ChatWidget, {
      global: {
        stubs: {
          RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
        },
      },
    })
    await wrapper.get('[data-testid="chat-toggle"]').trigger('click')
    await wrapper.get('textarea').setValue('  Tìm áo thun đen size M  ')
    await wrapper.get('form').trigger('submit')
    await vi.waitFor(() => expect(sendChatMessageMock).toHaveBeenCalledTimes(1))

    expect(sendChatMessageMock).toHaveBeenCalledWith('Tìm áo thun đen size M', [])
    expect(wrapper.get('[data-testid="chat-messages"]').text()).toContain('Tìm áo thun đen size M')
    expect(wrapper.get('[data-testid="chat-messages"]').text()).toContain('Áo thun đen còn hàng')
    expect(wrapper.get('[data-testid="chat-product-card"] a').attributes('href'))
      .toBe('/san-pham/ao-thun-den')
    expect(wrapper.get('[data-testid="chat-product-card"]').text()).toContain('249.000 ₫')
    expect(wrapper.get('[data-testid="chat-product-card"]').text()).toContain('Còn hàng')
    expect(wrapper.get('textarea').element).toHaveProperty('value', '')
  })

  it('announces provider status without inventing product cards', async () => {
    sendChatMessageMock.mockResolvedValue({
      answer: 'Dịch vụ tư vấn đang tạm gián đoạn. Vui lòng thử lại sau.',
      products: [],
      sources: [],
      status: 'provider_unavailable',
    })
    const wrapper = mount(ChatWidget)
    await wrapper.get('[data-testid="chat-toggle"]').trigger('click')
    await wrapper.get('textarea').setValue('Gợi ý áo khoác')
    await wrapper.get('form').trigger('submit')
    await vi.waitFor(() => expect(sendChatMessageMock).toHaveBeenCalledTimes(1))

    expect(wrapper.get('[data-testid="chat-status"]').text())
      .toBe('Dịch vụ tư vấn tạm thời không khả dụng')
    expect(wrapper.find('[data-testid="chat-product-card"]').exists()).toBe(false)
  })

  it('shows loading and recoverable network error states', async () => {
    let rejectRequest: ((reason?: unknown) => void) | undefined
    sendChatMessageMock.mockReturnValue(new Promise((_resolve, reject) => {
      rejectRequest = reject
    }))
    const wrapper = mount(ChatWidget)
    await wrapper.get('[data-testid="chat-toggle"]').trigger('click')
    await wrapper.get('textarea').setValue('Tìm váy dưới 500 nghìn')
    await wrapper.get('form').trigger('submit')

    expect(wrapper.get('[role="status"]').text()).toBe('Đang tìm sản phẩm…')
    expect(wrapper.get('textarea').attributes('disabled')).toBeDefined()

    rejectRequest?.(new Error('network down'))
    await vi.waitFor(() => expect(wrapper.get('[role="alert"]').text())
      .toBe('Không thể gửi câu hỏi lúc này. Vui lòng thử lại.'))
    expect(wrapper.get('textarea').attributes('disabled')).toBeUndefined()
  })

  it('keeps at most six prior turns and sends on Enter but not Shift+Enter', async () => {
    sendChatMessageMock.mockImplementation(async (content: string) => ({
      answer: `Trả lời ${content}`,
      products: [],
      sources: [],
      status: 'insufficient_data',
    }))
    const wrapper = mount(ChatWidget)
    await wrapper.get('[data-testid="chat-toggle"]').trigger('click')

    for (let index = 1; index <= 4; index += 1) {
      await wrapper.get('textarea').setValue(`Câu ${index}`)
      if (index === 1) {
        await wrapper.get('textarea').trigger('keydown', { key: 'Enter', isComposing: true })
        expect(sendChatMessageMock).not.toHaveBeenCalled()
        await wrapper.get('textarea').trigger('keydown', { key: 'Enter', shiftKey: true })
        expect(sendChatMessageMock).not.toHaveBeenCalled()
      }
      await wrapper.get('textarea').trigger('keydown', { key: 'Enter' })
      await vi.waitFor(() => expect(sendChatMessageMock).toHaveBeenCalledTimes(index))
    }

    expect(sendChatMessageMock.mock.calls[3]?.[1]).toHaveLength(6)
    expect(wrapper.findAll('.chat-widget__message')).toHaveLength(6)
  })
})
