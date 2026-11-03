export type CurrencyCode = 'VND'

export interface CartItem {
  item_id: string
  variant_id: string
  product_name: string
  variant_sku: string
  color_name: string
  size_code: string
  image_url: string | null
  unit_price: number
  quantity: number
  line_total: number
  available_stock: number
}

export interface Cart {
  cart_id: string
  version: number
  items: CartItem[]
  subtotal: number
  discount_amount: number
  shipping_fee: number
  total: number
  currency: CurrencyCode
}

export interface AddCartItemRequest {
  variant_id: string
  quantity: number
}

export interface UpdateCartItemRequest {
  quantity: number
  cart_version: number
}

export interface ShippingQuote {
  shipping_fee: number
  free_shipping_threshold: number
  currency: CurrencyCode
}

export type PaymentMethod = 'cod' | 'online_demo'
export type OrderStatus = 'pending_confirmation' | 'confirmed' | 'preparing' | 'shipping' | 'completed' | 'cancelled'
export type PaymentDemoStatus = 'pending' | 'cod_due' | 'paid_demo' | 'demo_processing' | 'demo_approved' | 'demo_declined' | 'cancelled'

export interface CreateOrderRequest {
  cart_id: string
  cart_version: number
  recipient_name: string
  phone: string
  address_line: string
  ward: string
  district: string
  province: string
  note?: string
  payment_method: PaymentMethod
  coupon_code?: string
  confirmation_token: string
}

export interface OrderSummary {
  order_code: string
  status: OrderStatus
  payment_method: PaymentMethod
  payment_status: PaymentDemoStatus
  subtotal: number
  discount_amount: number
  shipping_fee: number
  total: number
  currency: CurrencyCode
  success_url: string
  lookup_token?: string
}

export type OrderAccessContext =
  | { mode: 'authenticated' }
  | { mode: 'guest'; lookup_token: string }

export interface PaymentDemo {
  order_code: string
  provider: 'demo'
  method: PaymentMethod
  status: PaymentDemoStatus
  amount: number
  currency: CurrencyCode
}

export type RefundDemoStatus = 'requested' | 'demo_reviewing' | 'demo_approved' | 'demo_rejected' | 'cancelled' | 'demo_refunded'

export interface CreateRefundRequest {
  reason_code: string
  reason_detail?: string
  confirmation_token: string
}

export interface RefundRequest {
  order_code: string
  reason_code: string
  reason_detail: string | null
  amount: number
  currency: CurrencyCode
  status: RefundDemoStatus
  created_at: string
}
