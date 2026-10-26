export interface Category {
  id: string
  name: string
  slug: string
  description: string | null
  sort_order: number
}

export interface ProductColor {
  id: string
  name: string
  hex_code: string | null
}

export interface ProductSize {
  id: string
  code: string
  name: string
}

export interface ProductCardData {
  id: string
  slug: string
  sku: string
  name: string
  category: Category
  image_url: string | null
  price: number
  sale_price: number | null
  effective_price: number
  labels: string[]
  available_sizes: string[]
  available_colors: ProductColor[]
  in_stock: boolean
}

export interface ProductImage {
  id: string
  url: string
  alt_text: string | null
  sort_order: number
  is_primary: boolean
}

export interface ProductVariant {
  id: string
  sku: string
  color: ProductColor
  size: ProductSize
  stock_quantity: number
  is_available: boolean
}

export interface ProductDetail extends ProductCardData {
  description: string | null
  images: ProductImage[]
  variants: ProductVariant[]
}

export interface CatalogQuery {
  q?: string
  category?: string
  minPrice?: number
  maxPrice?: number
  color?: string
  size?: string
  page?: number
  pageSize?: number
}
