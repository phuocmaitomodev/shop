import { createMemoryHistory } from 'vue-router'
import { describe, expect, it } from 'vitest'

import { createAppRouter } from '../router'

Object.defineProperty(window, 'scrollTo', { value: () => undefined, writable: true })

const commerceRoutes = [
  ['/gio-hang', 'cart'],
  ['/thanh-toan', 'checkout'],
  ['/dat-hang-thanh-cong', 'order-success'],
  ['/tra-cuu-don-hang', 'order-lookup'],
  ['/don-hang/DH-001', 'order-detail'],
  ['/don-hang/DH-001/thanh-toan-demo', 'payment-demo'],
  ['/don-hang/DH-001/hoan-tien-demo', 'refund-demo'],
] as const

describe('commerce route shells', () => {
  it.each(commerceRoutes)('resolves %s to %s', (path, name) => {
    const router = createAppRouter(createMemoryHistory())
    const resolved = router.resolve(path)

    expect(resolved.name).toBe(name)
    expect(resolved.matched[0]?.components?.default).toBeTruthy()
  })
})
