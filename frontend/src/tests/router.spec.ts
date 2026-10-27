import { createMemoryHistory } from 'vue-router'
import { describe, expect, it } from 'vitest'

import PlaceholderPage from '../pages/PlaceholderPage.vue'
import { createAppRouter } from '../router'

const primaryRoutes = [
  '/',
  '/san-pham',
  '/danh-muc/ao-thun',
  '/san-pham/ao-thun-basic',
  '/gio-hang',
  '/thanh-toan',
  '/dat-hang-thanh-cong',
  '/dang-nhap',
  '/dang-ky',
  '/quen-mat-khau',
  '/dat-lai-mat-khau',
  '/tai-khoan',
  '/tai-khoan/don-hang',
  '/tai-khoan/don-hang/DH-001',
  '/admin',
  '/admin/san-pham',
  '/admin/don-hang',
  '/admin/khach-hang',
  '/admin/ma-giam-gia',
  '/admin/noi-dung-rag',
  '/admin/ho-tro',
  '/gioi-thieu',
  '/lien-he',
  '/chinh-sach-giao-hang',
  '/chinh-sach-doi-tra',
  '/cau-hoi-thuong-gap',
]

describe('application router', () => {
  it('uses the real product listing page for /san-pham', () => {
    const router = createAppRouter(createMemoryHistory())

    expect(router.resolve('/san-pham').matched[0]?.components?.default).not.toBe(PlaceholderPage)
  })

  it.each(primaryRoutes)('resolves %s to a named placeholder route', (path) => {
    const router = createAppRouter(createMemoryHistory())
    const resolved = router.resolve(path)

    expect(resolved.matched.length).toBeGreaterThan(0)
    expect(resolved.name).toBeTruthy()
    expect(resolved.name).not.toBe('not-found')
  })

  it('uses the not-found page for an unknown location', () => {
    const router = createAppRouter(createMemoryHistory())

    expect(router.resolve('/khong-ton-tai').name).toBe('not-found')
  })

  it('routes product slugs to the product detail page', () => {
    const router = createAppRouter(createMemoryHistory())
    const resolved = router.resolve('/san-pham/ao-thun-basic')

    expect(resolved.name).toBe('product-detail')
    expect(typeof resolved.matched[0]?.components?.default).toBe('function')
  })
})