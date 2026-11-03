export type CurrencyCode = 'VND'

export interface CartItem {
  item_id: string
  variant_id: string
  product_id: string
  product_slug: string
  product_name: string
  variant_sku: string
  color_name: string
  size_code: string
  unit_price: number
  previous_unit_price: number
  price_changed: boolean
  quantity: number
  line_total: number
  stock_quantity: number
  is_available: boolean
}

export interface Cart {
  cart_id: string
  version: number
  items: CartItem[]
  item_count: number
  coupon_code: string | null
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

export type PaymentMethod = 'cod' | 'online_demo'
export type OrderStatus = 'pending_confirmation' | 'confirmed' | 'preparing' | 'shipping' | 'completed' | 'cancelled'
export type PaymentDemoStatus = 'pending' | 'cod_due' | 'paid_demo' | 'demo_processing' | 'demo_approved' | 'demo_declined' | 'cancelled'

export interface CreateOrderRequest {
  cart_id: string
  cart_version: number
  recipient_name: string
  phone: string
  address_line: string
  ward: string | null
  district: string | null
  province: string
  note: string | null
  payment_method: PaymentMethod
  confirmation_token: string
}

export interface OrderSummary {
  id: string
  order_code: string
  status: OrderStatus
  recipient_name: string
  phone: string
  address_line: string
  ward: string | null
  district: string | null
  province: string
  note: string | null
  subtotal: number
  discount_amount: number
  shipping_fee: number
  total: number
  currency: CurrencyCode
  items: OrderItem[]
  payment: PaymentDemo
  guest_lookup_token: string | null
  created_at: string
}

export interface OrderItem {
  product_id: string | null
  variant_id: string | null
  product_name: string
  product_sku: string
  variant_sku: string
  color_name: string
  size_code: string
  image_url: string | null
  unit_price: number
  quantity: number
  line_total: number
}

export type OrderAccessContext =
  | { mode: 'authenticated' }
  | { mode: 'guest'; lookup_token: string }

export interface PaymentDemo {
  provider: 'demo'
  method: PaymentMethod
  status: PaymentDemoStatus
  amount: number
  is_simulation: true
}

export type RefundDemoStatus = 'requested' | 'demo_reviewing' | 'demo_approved' | 'demo_rejected' | 'cancelled' | 'demo_refunded'

export interface CreateRefundRequest {
  reason_code: string
  reason_detail: string | null
  confirmation_token: string
}

export interface RefundRequest {
  id: string
  order_code: string
  reason_code: string
  reason_detail: string | null
  amount: number
  status: RefundDemoStatus
  provider: 'demo'
  is_simulation: true
  created_at: string
}

export type ConfirmationAction = 'order_create' | 'order_cancel' | 'refund_request'

export interface ConfirmationResponse {
  confirmation_token: string
  expires_at: string
}
