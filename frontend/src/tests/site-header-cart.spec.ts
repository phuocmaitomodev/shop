import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const commerce = vi.hoisted(() => ({ getCart: vi.fn() }))
vi.mock('../services/commerce', () => commerce)

import SiteHeader from '../components/SiteHeader.vue'
import { lastChatAuthoritativeState, publishChatAuthoritativeState } from '../stores/chat-action'
import { useCartCountStore } from '../stores/cart-count'

const cart = {
  cart_id: 'cart-1',
  version: 1,
  items: [],
  item_count: 3,
  coupon_code: null,
  subtotal: 0,
  discount_amount: 0,
  shipping_fee: 0,
  total: 0,
  currency: 'VND' as const,
}

const mountHeader = (pinia = createPinia()) => mount(SiteHeader, {
  global: {
    plugins: [pinia],
    stubs: {
      RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
    },
  },
})

const accessibleName = (element: Element) => {
  const ariaLabel = element.getAttribute('aria-label')
  if (ariaLabel) return ariaLabel.trim()

  const clone = element.cloneNode(true) as HTMLElement
  clone.querySelectorAll('[aria-hidden="true"]').forEach((node) => node.remove())
  return clone.textContent?.replace(/\s+/g, ' ').trim() ?? ''
}

describe('SiteHeader cart count', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    lastChatAuthoritativeState.value = null
  })

  it('loads the authoritative cart count and renders it in both cart links', async () => {
    commerce.getCart.mockResolvedValue(cart)

    const wrapper = mountHeader()
    await flushPromises()

    expect(commerce.getCart).toHaveBeenCalledOnce()
    const cartLinks = wrapper.findAll('a[href="/gio-hang"]')
    expect(cartLinks).toHaveLength(2)
    expect(cartLinks.map((link) => link.text())).toEqual([
      'Giỏ hàng (3)',
      'Giỏ hàng (3)',
    ])
  })

  it('keeps a known count when loading the cart fails', async () => {
    commerce.getCart.mockRejectedValue(new Error('network unavailable'))
    const pinia = createPinia()
    useCartCountStore(pinia).syncCart({ ...cart, item_count: 5 })

    const wrapper = mountHeader(pinia)
    await flushPromises()

    expect(wrapper.findAll('a[href="/gio-hang"]').map((link) => link.text())).toEqual([
      'Giỏ hàng (5)',
      'Giỏ hàng (5)',
    ])
  })

  it('exposes the live count in the accessible name of both cart links', async () => {
    commerce.getCart.mockResolvedValue(cart)

    const wrapper = mountHeader()
    await flushPromises()

    expect(wrapper.findAll('a[href="/gio-hang"]').map((link) => accessibleName(link.element))).toEqual([
      'Giỏ hàng (3)',
      'Giỏ hàng (3)',
    ])
  })

  it('synchronizes both cart links from the authoritative cart refreshed after chat confirmation', async () => {
    commerce.getCart.mockResolvedValue(cart)
    const wrapper = mountHeader()
    await flushPromises()

    publishChatAuthoritativeState({
      kind: 'cart',
      action: 'cart_add',
      cart: { ...cart, version: 2, item_count: 6 },
    })
    await flushPromises()

    expect(wrapper.findAll('a[href="/gio-hang"]').map((link) => link.text())).toEqual([
      'Giỏ hàng (6)',
      'Giỏ hàng (6)',
    ])
  })
})
