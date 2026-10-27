import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createMemoryHistory } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../services/chat', () => ({ sendChatMessage: vi.fn() }))

import App from '../App.vue'
import { createAppRouter } from '../router'

Object.defineProperty(window, 'scrollTo', { value: () => undefined, writable: true })

describe('application shell', () => {
  it('renders the shared landmarks and chat widget position', async () => {
    const router = createAppRouter(createMemoryHistory())
    await router.push('/')
    await router.isReady()

    const wrapper = mount(App, {
      global: { plugins: [createPinia(), router] },
    })

    expect(wrapper.get('header').text()).toContain('Mộc Store')
    expect(wrapper.get('nav[aria-label="Điều hướng chính"]')).toBeTruthy()
    expect(wrapper.get('form[role="search"]')).toBeTruthy()
    expect(wrapper.get('nav[aria-label="Danh mục sản phẩm"]')).toBeTruthy()
    expect(wrapper.findAll('a[href="/tai-khoan"]')).toHaveLength(2)
    expect(wrapper.findAll('a[href="/gio-hang"]')).toHaveLength(2)
    expect(wrapper.get('main#main-content').text()).toContain('Khám phá phong cách')
    expect(wrapper.get('footer').text()).toContain('Dữ liệu cửa hàng mẫu')
    expect(wrapper.get('[data-testid="chat-widget-position"]')).toBeTruthy()
    expect(wrapper.get('[data-testid="chat-toggle"]').attributes('aria-expanded')).toBe('false')
    await wrapper.get('[data-testid="chat-toggle"]').trigger('click')
    expect(wrapper.get('[role="dialog"]').text()).toContain('Trợ lý sản phẩm')
  })

  it('provides valid destinations for every shell navigation link', async () => {
    const router = createAppRouter(createMemoryHistory())
    await router.push('/')
    await router.isReady()

    const wrapper = mount(App, {
      global: { plugins: [createPinia(), router] },
    })

    const hrefs = wrapper
      .findAll('a[href]')
      .map((link) => link.attributes('href'))
      .filter((href): href is string => Boolean(href))

    expect(hrefs.length).toBeGreaterThan(0)
    for (const href of hrefs) {
      const resolved = router.resolve(href)
      expect(resolved.matched.length, href).toBeGreaterThan(0)
      expect(resolved.name, href).not.toBe('not-found')
    }
  })
})
